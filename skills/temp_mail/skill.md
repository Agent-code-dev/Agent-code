---
name: temp_mail
description: Temporary email with multi-provider send and receive.
version: 1.0.0
author: abdo
---

# temp_mail

Temporary email that can both receive and send.

## Receive chain (tries in order)

  mail.tm          REST API, no signup, no captcha
  Guerrilla Mail   AJAX, receive only
  PhoboMail        MCP-based, send + receive

## Send (configure one with /email)

  Resend    100/day, 3000/mo    https://resend.com
  Brevo     300/day, 9000/mo    https://brevo.com
  Mailjet   200/day, 6000/mo    https://mailjet.com

The temp inbox address is attached as Reply-To on every send,
so replies land back in check_temp_inbox().

## Tools the LLM can call

  get_temp_email       create or return the temp address
  send_email           send from the temp address
  check_temp_inbox     list received messages
  read_temp_email      read one by ID
  reset_temp_email     rotate to a fresh address
  list_providers       show all send + receive providers

## Commands you can type

  /email                    show current status
  /email resend  <key>
  /email brevo   <key> <from@addr>
  /email mailjet <user> <secret> <from@addr>
  /providers                list all providers

## Setup (30 seconds)

  1. Sign up free at https://resend.com (no card)
  2. Copy your API key (starts with re_)
  3. In chat:   /email resend re_YOUR_KEY
  4. Try:       send hi to someone@example.com

Do NOT retry send_email before /email is configured.