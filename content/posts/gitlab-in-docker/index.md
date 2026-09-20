---
title: "GID - Gitlab in Docker"
date: 2024-08-06
draft: false
description: "Spinning up a self-hosted GitLab CE server and runner with Docker Compose"
tags: ["blog", "perso"]
aliases: ["/blogs/gitlab-in-docker/"]
---

Self-hosted GitLab CE plus a runner, both in Docker, no manual setup beyond `docker compose up`. Here's the compose file I use:

```yaml
version: '3.8'
services:

  gitlab-server:
    image: 'gitlab/gitlab-ce:latest'
    container_name: gitlab-server
    ports:
      - '8000:8000'
    environment:
      GITLAB_ROOT_EMAIL: "chxmxii.ctf@gmail.com"
      GITLAB_ROOT_PASSWORD: "v3ryl0ng&&secur3p455w0rd"
      GITLAB_OMNIBUS_CONFIG: |
        external_url 'http://localhost:8000'
        nginx['listen_port'] = 8000
    volumes:
      - ./gitlab/config:/etc/gitlab
      - ./gitlab/data:/var/opt/gitlab

  gitlab-runner:
    image: gitlab/gitlab-runner:alpine
    container_name: gitlab-runner
    network_mode: 'host'
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
```

```bash
docker compose up -d
```

## Access

GitLab comes up at `http://localhost:8000`. Log in with the email and password from the compose file above.

## Registering the runner

Register it with:

```bash
docker exec -it gitlab-runner gitlab-runner register
```

It'll walk you through a few prompts:

- **GitLab instance URL**: `http://localhost:8000`
- **Registration token**: You can find this in GitLab under `Admin Area > Runners`
- **Description**: Any label for this runner (e.g., `local-runner`)
- **Tags**: Optional tags (e.g., `docker`)
- **Executor**: Choose `docker` and set a default image (e.g., `alpine:latest`)

Once that's done, the runner starts picking up jobs from GitLab.