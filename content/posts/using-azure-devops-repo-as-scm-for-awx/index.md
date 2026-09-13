---
title: "Authenticating AWX with Azure DevOps using Personal Access Tokens"
date: 2024-12-04
draft: false
description: "How to set up Azure DevOps as a Git source for AWX"
tags: ["awx", "ansible", "blog"]
aliases: ["/blogs/using-azure-devops-repo-as-scm-for-awx/"]
---

## Intro

If you’ve ever tried syncing a Git repository from Azure DevOps into AWX, you’ve probably run into some weird issues. And the most annoying is that the sync job keep failing with an error message `fatal: Authentication failed`. Fortunately, And after struggling with this myself, I found a working solution worth sharing.

---

The main problem is that AWX doesn’t support the way Microsoft expects you to authenticate. Azure DevOps relies on personal access tokens (PATs) sent in an Authorization header when connecting to Git, as explained [here](https://learn.microsoft.com/en-us/azure/devops/organizations/accounts/use-personal-access-tokens-to-authenticate?view=azure-devops&tabs=Linux).

Many people suggest using SSH keys, but in many setups (like mine), SSH access is disabled for security reasons, And building a custom execution environment and injecting a Git config file into the container might work, but it felt like overkill for something that should be straightforward.


## Solution

After hours of testing and digging around, I discovered a helpful Git feature that lets you inject configuration dynamically at runtime. This is done using `GIT_CONFIG_COUNT`, `GIT_CONFIG_KEY_*`, and `GIT_CONFIG_VALUE_*`. (you can read more [here](https://git-scm.com/docs/git-config#Documentation/git-config.txt-GITCONFIGCOUNT))

All you need to do is pass these as environment variables to the job that performs the project sync. It should look like:

```json
{
  "GIT_CONFIG_COUNT": "1",
  "GIT_CONFIG_KEY_0": "http.extraHeader",
  "GIT_CONFIG_VALUE_0": "Authorization: Basic <your-base64-token>",
  "GIT_SSL_NO_VERIFY": "true"
}
```

To generate the value for `GIT_CONFIG_VALUE_0` use `printf ":$PAT" | base64`, please note that the username part before the colon is intentionally empty.

---

## Das Ende

This method lets you sync Azure DevOps Git repos in AWX using PATs without needing to modify containers or set up SSH. It worked well for me, and I hope it saves you the hours I spent trying to make this simple thing work.