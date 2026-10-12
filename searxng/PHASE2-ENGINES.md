# Phase 2 engine candidates (not yet enabled)

Stock modules, disabled. Enable pattern (settings.yml, then `docker restart firecrawl-searxng-1`):
    - name: <name>
      disabled: false
      weight: 0.4

## Books / shadow libraries (legal review before enabling)
annas archive (stock module, shortcut !aaa variants), library genesis, openlibrary

## Science / reference
openalex (chronically flaky from this IP - retest), wikispecies, wolframalpha (needs API key)

## General web
qwant (partially Bing-backed, rate-limit history), yahoo, yacy, etymonline, jisho, duden, woxikon.de synonyme

## Regional (own indexes)
yandex, baidu, sogou, naver, seznam, 360search, quark, fireball (DE), gmx, fastbot, searchch, vuhuv, resulthunter, tusksearch, privacywall

## News
google news, qwant news, tagesschau, ansa, il post, bpb, tagesschau

## Videos
vimeo, odysee, bilibili, niconico, rumble, media.ccc.de, mediathekviewweb (DE public TV), ina, iqiyi, acfun, bitchute, peertube

## Images
openverse, flickr, findthatmeme, frinkiac, imgur, giphy, tineye (reverse image), artic, artstation, ipernity, public domain image archive, magnific, pixabay

## Social / fediverse (lemmy+mastodon+tootfinder already ON)
boardreader, 9gag

## Movies / music / books / shopping / other
imdb, tmdb, rottentomatoes, moviepilot, senscritique, bandcamp, deezer, yandex music, goodreads, steam, emojipedia, erowid, geizhals, destatis, podchaser, fyyd, chefkoch

## Apps / package leftovers
apk mirror, apple app store, google play apps, fdroid, anaconda, alpine linux packages, cachy os packages, voidlinux, bitbucket, gitea.com, free software directory, habrahabr, discuss.python, caddy.community, pi-hole.community, ollama, huggingface datasets, huggingface spaces

## Weather / translate / map
openmeteo, duckduckgo weather, lingva, mozhi, dictzone, mymemory translated, apple maps

## Watch list
- metacpan: HTTP error on first pool query after enable (2026-10-12); disable if chronic
