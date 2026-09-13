---
title: "Certified Kubernetes Security Specialist PART II"
date: 2024-09-15
draft: false
description: "My certification notes for the CKS exam"
tags: ["certs", "kubernetes", "security", "cks"]
aliases: ["/kubernetes/Certified-Kubernetes-Security-Specialist-Part-II/"]
---
Continuing from [part I](/posts/cks-part-i/). This is **part II** of the CKS exam preparation series, where I will be exploring more topics related to securing Kubernetes clusters.

If you haven't read part I, I recommend you do so before continuing with this part.
[← Back to Part I](/posts/cks-part-i/)

## Supply chain security;

### Image Footprint

- Reduce footprint by using multistage dockerfile.
- This will eventually reduce the size of our final image.

```Dockerfile
# build stage (0)
FROM ubuntu
ARG DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y golang-go
COPY app.go .
RUN CGO_ENABLED=0 go build app.go

# runtime stage
FROM alpine
COPY --from=0 /app .
CMD ["./app"]
```
  
- We can make this more secure by;
    - using a specific versions of images. (stay away from latest/default). **A**
    - avoiding runing with the root container. **B**
    - make fs RO. **C**
    - remove shell access **D**
    

```Dockerfile
FROM ubuntu
ARG DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y golang-go
COPY app.go .
RUN CGO_ENABLED=0 go build app.go

# runtime stage
FROM alpine:3.12.1 (A)
RUN chmod a-w /etc (C)
RUN addgroup -S appgroup && adduser -G appgroup -h /home/appuser (B)
RUN rm -fr /bin/* (D)
COPY --from=0 /app /home/appuser/
USER appuser (B)
CMD ["/home/appuser/app"]
```
    

### Image Vulnerability Scanning

- Containers that contains exploitable packages are a problem, this could result in privesc, data leaks, ddos etc..
- Keeping an eye on your image safety is very important, so is good to do a check during the build and run time. (scan the registry when image is pushed, enforce at deploy time using OPA).
- tools;
    - Clair: opensorce vuln assessment tool, CNCF supported.
    - trivy: simple to use, one cmd to run it;

    `$ docker run ghcr.io/aquasecurity/trivy:latest image nginx`

### Static Analysis

- look at the source code and text files and parses them to check against rules and later enforce them, eg;
    - define requests & limits
    - never use sa default
    - never store sensitive data in plain text in dockerfiles or k8s resources.
- When to do the SA? for a good coverage it is recommened to do it;
    - before commiting
    - before build
    - during test phase
    - at the deploy phase using admission controller like OPA.
- **Manual approach;**
    - Simply by going through the source code and the text files.
- **Tools;**
    - **kubesec.io**;
        - opensource
        - does a score and recommend improvements
        - simple to use; `docker run -i kubesec/kubesec:512c5e0 scan /dev/stdin < ./pod.yaml`
    - **OPA conftest**;
        - Used against dockerfiles
        - Offered by OPA (uses same languge rego).
        - run using the followin cmd; `docker run --rm -v $(pwd):/project openpolicyagent/conftest test Dockerfile --all-namespaces`
        - examples;
            
            ```go
            # from https://www.conftest.dev
            package main
            
            denylist = [
              "ubuntu"
            ]
            
            deny[msg] {
              input[i].Cmd == "from"
              val := input[i].Value
              contains(val[i], denylist[_])
            
              msg = sprintf("unallowed image found %s", [val])
            }
            ---
            package commands
            
            denylist = [
              "apk",
              "apt",
              "pip",
              "curl",
              "wget",
            ]
            
            deny[msg] {
              input[i].Cmd == "run"
              val := input[i].Value
              contains(val[_], denylist[_])
            
              msg = sprintf("unallowed commands found %s", [val])
            }
            ```

### Secure Supply Chain

Secure supply chain helps us ensure that the images, libs, and other dependencies we use are safe and free from vulnerabilities.

### K8S & Container Regisitires;

- **PrivateRegistires**; create a `docker-registry` secret in kubernetes and then associate the `imagePullSecrets` to the SA.
- Container images can be run using image digest instead of a tag. e.g;
    
    ```yaml
      containerStatuses:
      - containerID: containerd://87cf84840ab758c375988491da7e71bb8c78ea435d92ccb41fe05aae19d62eae
        image: k8s.gcr.io/kube-apiserver:v1.20.2
        imageID: sha256:3ad0575b6f10437a84a59522bb4489aa88312bfde6c766ace295342bbc179d49
    ```
    

### AllowList Registries w/OPA;

- You could use OPA to limit images to specific repos.
- Constraint Templates;
    
    ```yaml
    apiVersion: templates.gatekeeper.sh/v1beta1
    kind: ConstraintTemplate
    metadata:
      name: k8strustedimages
    spec:
      crd:
        spec:
          names:
            kind: K8sTrustedImages
      targets:
        - target: admission.k8s.gatekeeper.sh
          rego: |
            package k8strustedimages
    				#if all conds are true, then violation is thrown && the pod creation is denied.
            violation[{"msg": msg}] {
              image := input.review.object.spec.containers[_].image
              not startswith(image, "docker.io/") 
              not startswith(image, "k8s.gcr.io/")
              msg := "not trusted image!"
            }
    ```
    
    ```yaml
    apiVersion: constraints.gatekeeper.sh/v1beta1
    kind: K8sTrustedImages
    metadata:
      name: pod-trusted-images
    spec:
      match:
        kinds:
          - apiGroups: [""]
            kinds: ["Pod"]
    ```
    

### ImagePolicyWebhook;

`ApiServer` ↔ `AdmissionContollers` ↔ `ImagePolicyWebhook` ↔ `External Service`

- `ImagePolicyWebhook` creates a kind of `ImageReview` which can be assessed by an external tool as part of an admission workflow.
- You can enable the imagePolicyWebhook via the kube-api manifest;
    - `--enable-admission-plugins=ImagePolicyWebhook`
    - Create a dir to house all ur admission conf. /etc/kuberentes/admision.
    - `--admission-control-config-file=path-to-admission-config.`
    - add hostPath and **volumeMount** to mount the **admissionDir** so all your config files are available within the container.
    
    ```yaml
    apiVersion: apiserver.config.k8s.io/v1
    kind: AdmissionConfiguration
    plugins:
      - name: ImagePolicyWebhook
        configuration:
          imagePolicy:
            kubeConfigFile: /etc/kubernetes/admission/kubeconf
            allowTTL: 50
            denyTTL: 50
            retryBackoff: 500
            defaultAllow: false # important: if `true`, then if policy webhook can't be reached will just allow the image.
    ```
    
    kubeconf e.g;
    
    ```yaml
    apiVersion: v1
    kind: Config
    
    # clusters refers to the remote service.
    clusters:
    - cluster:
        certificate-authority: /etc/kubernetes/admission/external-cert.pem  # CA for verifying the remote service.
        server: https://external-service:1234/check-image                   # URL of remote service to query. Must use 'https'.
      name: image-checker
    
    contexts:
    - context:
        cluster: image-checker
        user: api-server
      name: image-checker
    current-context: image-checker
    preferences: {}
    
    # users refers to the API server's webhook configuration.
    users:
    - name: api-server
      user:
        client-certificate: /etc/kubernetes/admission/apiserver-client-cert.pem     # cert for the webhook admission controller to use
        client-key:  /etc/kubernetes/admission/apiserver-client-key.pem             # key matching the cert
    ```

## Monitoring, Logging & Runtime Security;
### Immutability of containers at runtime

- Immutability means the container won’t be modified during its lifetime. (u always know the state).
- Working with immutable containers offers a more reliable/stable workload, easy rollback, and a better security.
- to enfore the immutability;
    - remove shells from the image.
    - set readOnlyRootFilesystem to true.
    - Make sure to runAsNonRoot.
- If you don’t have control on the container then;
    - use **startipProbe** to remove shells on the way up.
    - use of **securityContext**.
    
    ```yaml
    #e.g. startupProbe
    spec:
      containers:
      - image: nginx
        name: pod
        resources: {}
        startupProbe:
          exec:
            command:
            - rm
            - /bin/bash
          initialDelaySeconds: 5
          periodSeconds: 5
       
     #e.g. securityContenxt
     spec:
      containers:
      - image: httpd
        name: immutable
        resources: {}
        securityContext:
          readOnlyRootFilesystem: true
          
        #if u want to write to a dir, then u'hv to create an emptyDir{} vol nd mount it. 
          
    ```
    

### Behavioral Analytics at host and container level

- kube admins should keep an eye on potential malicious activity. this can be done manually by loggin into the cluster nodes and observing host and contianer level process, or by using tools like falco.
- behavioral analytics is the process of observing the cluster nodes for any activity that seems malicious. an automated process can be helpful with filtering, recording, and alerting events of specific interest. (falco,trace,tetragon)
- so what is falco?
    - Cloudnative runtime security tool uses deep kernel tracing to detect bad behavior and automate response to any violations.
    - Falco arch;
    - Falco deploys a set of rules (sensor) that maps an event to a data source.
    - Falco allows enabling more tha one output channel simultaneously.

```yaml
# /etc/falco/falco_rules.yaml
#to edit the output of logs go /etc/falco/falco.yaml
- rule: shell_in_container
 desc: notice shell activity within a container
 condition: evt.type = execve and evt.dir=< and container.id != host and proc.name = bash
 output: shell in a container (user=%user.name container_id=%container.id container_name=%container.name ↵
 shell=%proc.name parent=%proc.pname cmdline=%proc.cmdline)
 priority: WARNING
 
 # journalctl -uxef falco
```

### Auditing

- Why?
    - What event occurred and by who?
    - Debugging apps/crds.
- Audit;
    - **Policy;** Defines the type of event and the corresponding request data to be recorded.
    - **Backend;** Responsible for storing the recorded audit events as defined by the audit policy.
        - Writes events to a file.
        - Triggeres a webhook which sends the events to an external service via HTTP(S) for a centralized logging and monitoring system.
    
    ```yaml
    apiVersion: audit.k8s.io/v1
    kind: Policy
    omitStages: #Prevents generating logs for all requests in this stage.
     - "RequestReceived"
    rules:
     - level: RequestResponse #Logs pod changes at ReqRes levle
    	 resources:
    	 - group: ""
    		 resources: ["pods"]
     - level: Metadata #Logs Pod events at the metadata level e.g log and status req (user,timestamp, res,verb) but not the req/rep body.
    	 namespace: ["dev"]
    	 resources:
    	 - group: ""
    		 resources: ["pods/log", "pods/status"]
    ```
    
    - To enable auditing, you will have to;
    
    ```yaml
    spec:
    	containers:
    	- command:
    	  - kube-apiserver
    	  - --audit-policy-file=/etc/kubernetes/x.yml
    	  - --audit-log=x.log=/var/log/kubernetes/y.log
    	  - --audit-log-maxsize=500                                     
        - --audit-log-maxbackup=5                                     
    
      ...
    	  volumeMounts:
    	  - mountPath: /etc/kubernetes/x.yml
    		  name: audit-policy
    		  readOnly: true
    	 volumeMounts:
    	  - mountPath: /var/log/kubernetes/
    		  name: audit-log
    		  readOnly: false
     ...
     volumes:
     - name: audit-policy
    	 hostPath:
    		 path: /etc/kubernetes/x.yml
    		 type: File
     - name: audit-policy
    	 hostPath:
    		 path: /var/log/kubernetes
    		 type: DirectoryOrCreate
    ```
    

### Kernel Hardening Tools

- Apps/Process running inside of a container can mae system calls. for e.g. a curl command that performs a http request.
- curl → libs → seccomp/apparmor → syscall → os kernel → hw.
- a syscall is a programmatic abstraction running in the userspace for requesting a service from a kernel.
- **AppArmor;**
    - An additional security layer between the app invoked in the user space and the uderlying system functionality.
    - creates various profiles to allow/restrict what an app can do to fs,ps,networks etc..
        - unconfined → Allow escape
        - complain → process can escape but log.
        - enforce → no escape
    - **cmds;**
        - `aa-status` → list loaded profiles.
        - `apparmor_parser -q /path/to/profile` → load an aa profile.
        - `aa-logprof` → scans log files for apparmor events ot covered by a profile.
        
        ```yaml
        #AppArmor in k8s
        #before
        annotations:
            container.apparmor.security.beta.kubernetes.io/aa-pod: localhost/docker-nginx
        ...
        #settings in sc
        securityContext:
        	AppArmorProfile:
        		type: Localhost
        		localhostProfile: docker-nginx
        
        ```
        
- **Seccomp;**
    - stands to secure computing, used to sandbox the privileges of a process.
    - restricts the calls made from the userspace into the kernel space.
    - Originally allows 4x calls [”exit()”,”sigreturn()”,”read()”,”write()”].
    
    ```yaml
    ...
    spec:
      securityContext:
        seccompProfile:
          type: Localhost
          localhostProfile: default.json
    ```
    

### Reduce Attack Surface

What is an attack surface?

- apps should be kept uptodate, unneeded packages should be removed.
- networks; close ports, keep everything behind a firewamm.
- iam - restrict user perms. don’t run as root.
- lot of services = more attack surface

Within kubernetes;

- run k8s components only.
- keep all the workload ephermal.
- create from images

So what to do?

- Disable, and stop unecessary services.
    - systemctl, service. e.g `systemctl list-units -t service --state=running`
- Close Ports
    - lsof, netstat, ss
- Delete packages
    - apt remove, search.

---

The exam was updated after I took it, so some of the topics might not be relevant anymore. other than that, new topics were added to the exam, such as;
- **SBOMs;** Software Bill of Materials.
- **Network Policies;** w/p2p encryption using cillium.
- **Linting;** using kubeLinter.

I hope this series was helpful to you, and I wish you the best of luck in your CKS exam!

{{< alert icon="-" cardColor="#42445A" textColor="white"  >}}
**References:**
- [Kubernetes.io](https://kubernetes.io)
- [Falco](https://falco.org)
- [OPA](https://www.openpolicyagent.org)
- [cillium](https://cilium.io)
- [kubesec.io](https://kubesec.io)
- [trivy](https://trivy.dev)
{{< /alert >}}