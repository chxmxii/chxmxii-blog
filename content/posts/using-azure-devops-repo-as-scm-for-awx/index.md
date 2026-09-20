---
title: "Authenticating AWX with Azure DevOps using Personal Access Tokens"
date: 2024-12-04
draft: false
description: "Fixing the fatal: Authentication failed error when you point AWX at an Azure DevOps Git repo"
tags: ["awx", "ansible", "blog"]
aliases: ["/blogs/using-azure-devops-repo-as-scm-for-awx/"]
---

## Intro

Try syncing a Git repo from Azure DevOps into AWX and you'll likely hit the same wall I did: the sync job dies with `fatal: Authentication failed`, every time, no matter how many times you double-check the token. It took me a few hours of digging to find a fix, so here it is.

---

The root problem is that AWX doesn't speak the auth flow Microsoft expects. Azure DevOps wants personal access tokens (PATs) sent in an Authorization header, [as documented here](https://learn.microsoft.com/en-us/azure/devops/organizations/accounts/use-personal-access-tokens-to-authenticate?view=azure-devops&tabs=Linux) — AWX just doesn't do that natively.

SSH keys are the usual workaround people suggest, but that's off the table if SSH access is locked down in your setup, which it is in mine. Building a custom execution environment and baking a Git config file into the container would work too. It's also way more effort than a straightforward auth problem deserves.

## Solution

Git has a feature most people never touch: injecting config at runtime through environment variables — `GIT_CONFIG_COUNT`, `GIT_CONFIG_KEY_*`, and `GIT_CONFIG_VALUE_*`. ([Documented here](https://git-scm.com/docs/git-config#Documentation/git-config.txt-GITCONFIGCOUNT) if you want the full picture.) That's the way in.

All you need to do is pass these as environment variables to the job that performs the project sync. It should look like:

```json
{
  "GIT_CONFIG_COUNT": "1",
  "GIT_CONFIG_KEY_0": "http.extraHeader",
  "GIT_CONFIG_VALUE_0": "Authorization: Basic <your-base64-token>",
  "GIT_SSL_NO_VERIFY": "true"
}
```

Generate `GIT_CONFIG_VALUE_0` with `printf ":$PAT" | base64`. Yes, the colon comes before an empty username — that's intentional, not a typo.

---

## Das Ende

No container rebuilds, no SSH setup, just PATs doing what they're supposed to do. This worked well for me on the first real try. If it saves you the hours I burned on it, good.