---
skill_id: bad-skill
version: "0.5"
author: ""
description: "too short"

# Permissions are deliberately dangerous
permissions:
  filesystem:
    read:
      - "/**"
      - "~/whatever"
    write:
      - "/**"
  network:
    domains:
      - "*"
    ports: []
    protocols: []
  tools: []
  credentials:
    - name: SOME_KEY
      scope: admin

cost:
  token_estimate:
    base: 0
  api_cost_risk: "WHATEVER"

input:
  required:
    - name: "x"
      type: "blob"
  optional:
    - name: "y"
      type: "string"

output:
  success:
    description: "ok"

tags: "this_should_be_an_array_not_string"
---

This is a deliberately bad skill with many issues.
