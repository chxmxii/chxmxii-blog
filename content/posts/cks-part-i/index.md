---
title: "Certified Kubernetes Security Specialist PART I"
date: 2024-08-29
draft: false
description: "CKS exam notes, part I — cluster setup, network policies, RBAC, secrets encryption, and container runtime sandboxing"
tags: ["certs", "kubernetes", "security", "cks"]
aliases: ["/kubernetes/Certified-Kubernetes-Security-Specialist-Part-I/"]
---
These are my notes from prepping for the **CKS** exam, kept high-level rather than exhaustive on every topic. This is **part I** of the series, and I'll keep adding to it as I go.

It's a performance-based exam: 2 hours, 15-20 questions, 66% to pass, and it actually tests whether you can secure a cluster rather than just describe how to.

More detail lives on the [CNCF website](https://www.cncf.io/certification/cks) if you're weighing whether to take it:

{{< button href="https://www.cncf.io/certification/cks" target="_self" >}}
CNCF WEBSITE
{{< /button >}}

For prep, [Kim's course](https://www.youtube.com/watch?v=d9xfB5qaOfg&t=39920s) on YouTube is worth your time, and **Killercoda**'s [CKS scenarios](https://killer.sh/cks) cover the exam's full topic list.

## Cluster Setup;
### GUI Elements;
- Only expose externally when necessary. or just use `kubectl port-forward`.
- kubectl proxy;
    - Establish proxy connection between localhost and the api server. (uses kubeconfig to communicate with the api server).
    - Allows access to api locally over http.
    - `localhost -> kubectl proxy -> kubectl (https) -> k8s api`
- kubectl port-forward;
    - maps the localhostPort to the podPort.
    - `localhost -> kubectl port-forward -> kubectl -> apiserver -> podPort`
    - Install and expose the kube dashboard externally (not recommended).
    ```shell
    root@localhost:~ kubectl apply -f https://raw.githubusercontent.com/kubernetes/dashboard/v2.3.1/aio/deploy/recommended.yaml
    root@localhost:~ k get pod,svc -n kubernetes-dashboard
    #for external access add the following line "--insecure-port=9090" to the arg inside the deployment
    root@localhost:~ k edit -nkubernetes-dashboard dashboard
    "spec:
        containers:
        - args:
            - --namespace=kubernetes-dashboard
            - --insecure-port=9090
            image: kubernetesui/dashboard:v2.3.1"
    #Patch the service type to nodePort.
    ```
⇒ You should now be able to reach the dashboard.

### Network Policies;
By default, pods aren't isolated at all. Every pod can talk to every other pod. Network Policies are how you fix that:
- Think of them as firewall rules for Kubernetes.
- Implemented by CNIs.
- Namespace-scoped.
- Allow/Deny (ingress/egress) traffic for pods based on specific criteria.
```yaml
kind: NetworkPolicy
metadata:
  name: 'example'
  namespace: 'default' # <-- policy applies to this namespace
spec:
  podSelector:
    matchLabels:
      id: 'frontend' # <-- applied to these pods as the SUBJECT/TARGET
    policyTypes:
    - Egress
    egress:

    # RULE 1.
    - to: # to AND ports i.e. id=ns1 AND port=80
      - namespaceSelector:
          matchLabels:
            id: 'ns1'
      ports:
      - protoco: 'TCP'
        port: 80

    # RULE 2.
    - to:
      - podSelector:
          matchLabels:
            id: 'backend' # <-- applies to these pods in SAME namespace where the policy lives, unless otherwise specified with a `namespaceSelector` label here.
```
Deny all ingress/egress traffic.
```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: default-deny
  namespace: default
spec:
  podSelector: {}
  policyTypes:
  - Egress
  - Ingress
```
{{< alert >}} Make sure to leave DNS port 53TCP/UDP open for address resolution.{{< /alert >}}

### Secure Ingress;
- Ingress is a single entry point into the cluster, that you can configure to route to different services within your cluster based on the URL path, and SSL termination. Basically a **Layer 7 Load Balancer** managed within the cluster**.**
- Once you create the resource object, an nginx config is generated inside the nginx-controller pod which then manages the routing rules.
```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: minimal-ingress
  annotations:
    nginx.ingress.kubernetes.io/rewrite-target: /
spec:
 tls:
  - hosts:
      - secure-ingress.com
    secretName: secure-ingress
  rules:
  - http:
      paths:
      - path: /testpath
        pathType: Prefix
        backend:
          service:
            name: test
            port:
              number: 80
     
# curl -vk https://secure-ingress.com:31926/service2 --resolve secure-ingress.com:31926:35.244.67.113
```
### Node Metadata Protection;
- metadata service run by provider and reachable from the VMs.
- Can house sensitive data like kubelet creds.
- Create NP to restrict access.
```yaml
root@cks-master:~# curl "http://metadata.google.internal/computeMetadata/v1/instance/disks/" -H "Metadata-Flavor: Google"
0/
root@cks-master:~ cat << EOF kubectl apply -f -
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: cloud-metadata-deny
  namespace: default
spec:
  podSelector: {}
  policyTypes:
  - Egress
  egress:
  - to:
    - ipBlock:
        cidr: 0.0.0.0/0
        except:
        - 169.254.169.254/32
EOF
```

### CIS Benchmarks;
- The CIS (Center for Internet Security) publishes secure configuration guidelines for a long list of platforms and systems, Kubernetes included.
- Follow the PDF guideline by hand, or download and run the benchmark binary.
- Tools like kube-bench scan your cluster against those benchmarks and flag any misconfiguration.

---

## Cluster Hardening;
### Role Based Access Control;
- RBAC is the use of (Cluster)Roles, (Cluster)RoleBindings, and Service Accounts to shape granular access to Kubernetes resources.
- Roles defines the permissions at the namespace level, whereas clusterroles defines the permissions at the cluster level.
- (Cluster)RoleBinding defines who gets them.
- Valid combinations
|Role Type | Binding Type | Scope |
|------|-------------|------------|
| Role | RoleBinding | Namespaced |
| clusterRole | clusterRoleBinding | Cluster-wide|
|clusterRole | roleBinding | Namespaced |

- Example;
```yaml
# Create a role
$ k -n red create role secret-manager --verb=get --resource=secrets -oyaml --dry-run=client
# Create a clusterRole
$ k -n red create rolebinding secret-manager --role=secret-manager --user=jane -oyaml --dry-run=client
# check permissions
k auth can-i <verb> <resources> --as <user/sa>
```

### Service Accounts & Users;
#### Users;
- Kubernetes doesn’t manage users, instead you create a certificate && key for a specific user and assign the necessary permissions using RBAC.
    1. openssl csr from user
    2. create csr resource to k8s api
    3. k8s-api signs the csr with ca
    4. crt is then available to download
    
=> 🔒 The user's "client cert" must be signed by the k8s CA, and the username is whatever sits under the `/CN=*username*` part of the cert.

{{< alert cardColor="#e63946" iconColor="#1d3557" textColor="#f1faee" >}}It is important to know that there is no way to invalidate a cert, once created, stays valid. Hence, if cert is leaked then either remove all access via RBAC, 2/ create new CA and re-issue all certs. {{< /alert >}}

#### Service Accounts;
- ServiceAccounts are used by bots,pods created by the k8s API.
- By default, there is a default service account created on every namespace. which is then automounted to every new created pods.
- You can disable automounting of a ServiceAccount `automountServiceAccountToken: false`.

### Restrict API access;

When a request is made to the k8s-api, it goes through the following:
- Who are you? → Authentication
- What are you allowed to do? → Authorization
- Admission controller (validating/mutating webhooks)
These requests are treated as;
- A normal user
- A serviceAccount
- Anonymous access.
{{< alert cardBackground="transparent" textColor="white" >}}
to disable anonymous access, set the `--anonymous-auth`flag to false with the kubelet manifest.
the `--insecure-port` is set to 0 by default, which disables the insecure port. (only bypasses AuthN and AuthZ mods).
{{< /alert >}}

- Do’s;
    - Don’t allow anonymous access/insecure port. (anonymous-access is needed since liveness pods need it for calling k8s api anonymously).
    - Don’t expose ApiServer to the internet.
    - Restrict access from node. (nodeRestriction).
- `k config view --raw` to view the config file. (--embed-certs for a cleaner output).

**NodeRestriction Admission Controller**;
- A common reason to enable the NodeRestriction admission plugin is to prevent the worker node from labeling the master node. to do that, you have to add the following argument to the kubeapi manifest file. `--enable-admission-plugins=NodeRestriction`.


## Microservices vulnerabilities;
### Manage Kubernetes Secrets;
- **Encrypt ETCD at rest;**
    - The only component allowed to talk to ETCD is kube-api, hence it is responsible for encrypt/decrypt in this flow.
    - To enable encryption at rest for a specific resource create a new api object with kind `EncryptionConfiguration.`
    
    ```bash
    # generate a key using the following command $( head -c 32 /dev/urandom | base64)
    apiVersion: apiserver.config.k8s.io/v1
    kind: EncryptionConfiguration
    resources:
      - resources:
        - secrets
        providers:
        - aescbc:
            keys:
            - name: key1
              secret: ffGddeJabcKMocX07jGu1hcL8bdggjH2PSIs24=
        - identity: {} #this is important to get etcd working with unencrypted secrets
    ```
    
    ```yaml
    #update the kube-apiserver.yaml manifest to include the provider config:
    #add the arg
    spec:
      containers:
      - command:
        - kube-apiserver
        - --encryption-provider-config=/etc/kubernetes/etcd/encEtcd.yaml
    #add the volume mount;
    ...
      volumeMounts:
      - mountPath: /etc/kubernetes/etcd
        name: etcd
    # add volume;
      volumes:
      - hostPath:
          path: /etc/kubernetes/etcd
          type: DirectoryOrCreate
        name: etcd
    ```
    
{{< alert cardColor="#e63946" iconColor="#1d3557" textColor="#f1faee"  >}}
if you need to troubleshoot you can go through the logs within the /var/log/pods dir.
{{< /alert >}}    

### Container runtimes sandboxing;
- Containers are run on a shared kernel, which enables us to execute syscalls (api-like to com w/kernel) that allow us to access other containers.
- Sandboxes in the security context is an additional layer to ensure isolation.
- Sandboxes come at a price: more resource overhead, and they're rough on heavy syscall workloads.

#### kata containers;

- container runtime sandbox (Hypervisor/VM based).

#### gVisor;

- a userspace kernel for containers from google.
- Interrupts to limit the syscalls sent by the user (app1↔syscalls↔gvisor↔limited syscalls↔host kernel ↔hw)

```yaml
apiVersion: node.k8s.io/v1  # RuntimeClass is defined in the node.k8s.io API group
kind: RuntimeClass 
metadata:   # RuntimeClass is a non-namespaced resource
  name: gvisor # The name the RuntimeClass will be referenced by
handler: runsc # The name of the corresponding CRI configuration
---
...
kind: Pod
#Next time you create a new pod make sure to include the runtimeClassName
spec: 
	runtimeClassName: gvisor
	containers:
	..
```
### OS level domains;
#### Pod Security Context;
- controls uid,gi at the pod/container level.

```yaml
spec:
    #pod level
    securityContext:
    runAsUser: 1000
    runAsGroup: 3000
    containers:
    - command:
    ...
    ...
        #container level
    securityContext:
        runAsNonRoot: true
    dnsPolicy: ClusterFirst
```
    
#### Privileged;
- maps container user with the host user (root).
enable w/docker `d run --privileged`
    
```yaml
spec:
    containers:
    - command:
    ...
    ...
    securityContext:
        privileged: true
```
        
#### Privilege Escalation;
- by default, k8s allows privesc via `allowPrivilegeEscalation`, to disable set to false within the **securityContext** field.
```yaml
spec:
    containers:
    - command:
    ...
    ...
    securityContext:
        allowPrivilegeEscalation: false
```

#### Pod Security Policies;

- Enable via kube-apiserver manifest file `--enable-admission-plugins=NodeRestriction,PodSecurityPolicy.`

```yaml
apiVersion: policy/v1beta1
kind: PodSecurityPolicy
metadata:
    name: default
spec:
    privileged: false  # Don't allow privileged pods!
    allowPrivilegeEscalation: false # added
    # The rest fills in some required fields.
    seLinux:
    rule: RunAsAny
    supplementalGroups:
    rule: RunAsAny
    runAsUser:
    rule: RunAsAny
    fsGroup:
    rule: RunAsAny
    volumes:
    - '*'
```
        
{{< alert cardColor="#757C88" iconColor="#1d3557" textColor="white"  >}}        
if psp is enabled, then it will be enforced on all resources. but the creator of the resource requires to see this default psp to use it.
a common approach to solve the problem (when creating a deploy is failed cuz the deploy resource doesn’t have admin perms to read the psp to create the resource) is to give the default sa to the psp.
`k create role psp-access --verb=use --resource=podsecuritypolicies`
`k create rolebinding psp-access --role=psp-access --serviceaccount=default:default`
{{< /alert >}}

### mTLS;

- mutual auth
- pod2pod encrypted communication
- both apps have client+server certs to communicate.

#### Service Meshes;

- manage all the certs between pods.
- decouple our app container from the auth/cert workload.
- all traffic is routed through a proxy/sidecar.

⇒ These routes are created via `iptable` rules. the sidecar needs the NET_ADMIN cap.

```yaml
apiVersion: v1
kind: Pod
metadata:
  creationTimestamp: null
  labels:
    run: app
  name: app
spec:
  containers:
  - command:
    - sh
    - -c
    - ping google.com
    image: bash
    name: app
    resources: {}
  - command:
    - sh
    - -c
    - 'apt-get update && apt-get install -y iptables && iptables -L && sleep 1d'
    securityContext:
      capabilities:
        add: ["NET_ADMIN"] #important for the proxy container
    image: ubuntu
    name: proxy
    resources: {}
  dnsPolicy: ClusterFirst
  restartPolicy: Always
status: {}
```

**Part II** picks up from here with the more advanced topics.

[Continue to Part II →](/posts/cks-part-ii/)