---
name: public_api
description: Search free public APIs and call them.
version: 1.0.0
author: abdo
---

# public_api

Search a catalog of 700+ free public APIs and call them directly.

## Source

  https://public-api-lists.github.io/public-api-lists/api/all.json

Cached to %TEMP%/public_apis.json on first use. No auth, no
rate limit, 48 categories.

## Tools the LLM can call

  search_apis(query, category, no_auth_only, limit)
      Find APIs matching a keyword or category.
      no_auth_only=True skips ones that need an API key.

  call_api(url, max_chars)
      GET a URL and return the first N chars of the body.
      Use for raw JSON endpoints only.

## Example

  User: find a free API for cat facts and call it
  Agent:
    search_apis(query="cat facts")
      → catfact.ninja | auth=No | https://catfact.ninja/
    call_api(url="https://catfact.ninja/fact")
      → {"fact": "An adult lion's roar..."}

## Rules the agent follows

  • Prefer APIs with auth == "No"
  • Never fabricate URLs — only use ones returned by search
  • Use the browser for HTML pages, call_api for raw JSON