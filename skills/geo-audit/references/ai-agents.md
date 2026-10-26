# AI agents in robots.txt

## Why two kinds

Vendors publish several user-agent tokens with different roles. Roughly:

- **Search / retrieval agents** fetch pages to answer or cite in live answers.
- **Training crawlers** collect content for model training.
- **User-triggered fetchers** load a page because a user asked the assistant to.
- **Control tokens** exist only to express a robots.txt preference, without a crawler of their own.

Blocking training is a legitimate choice that the skill does not judge. Blocking a search agent
can remove the site from that assistant's live answers: report it as a finding.

## Tokens to check — read on vendor pages on 2026-10-24, re-check before use

Read on each vendor's own documentation on 2026-10-24. Names, roles and whether a token honours
robots.txt change: at run time, re-open the pages below, compare, and date the reading.

| Vendor | Token | Role | robots.txt, as the vendor states it |
|---|---|---|---|
| OpenAI | `OAI-SearchBot` | search: sites that disallow it "will not be shown in ChatGPT search answers" | honoured |
| OpenAI | `GPTBot` | training | honoured (training opt-out) |
| OpenAI | `ChatGPT-User` | user-triggered; "not used to determine whether content may appear in Search" | "may not apply" |
| OpenAI | `OAI-AdsBot` | checks pages submitted as ads; not training | not stated; not an AI-visibility token |
| Anthropic | `Claude-SearchBot` | search | honoured |
| Anthropic | `ClaudeBot` | training | honoured |
| Anthropic | `Claude-User` | user-triggered | honoured (one statement for all three bots, Crawl-delay supported) |
| Perplexity | `PerplexityBot` | search; "not used to crawl content for AI foundation models" | not stated explicitly |
| Perplexity | `Perplexity-User` | user-triggered | "generally ignores robots.txt rules" |
| Mistral | `MistralAI-Index` | search: "automated crawling of the web for indexing purposes only" (Mistral search); "not used for generative AI training of any kind" (read 2026-10-25) | not stated explicitly |
| Mistral | `MistralAI-User` | user-triggered: "for user actions in Vibe" (Le Chat was renamed Vibe on 2026-08-12); not used to crawl automatically nor for training | not stated explicitly |
| Mistral | `MistralAI-Training` | training: "Webmasters can disallow this user agent in their robots.txt file." | honoured (training opt-out) |
| Google | `Googlebot` | Search, including AI Overviews and AI Mode: Google names Googlebot's robots.txt rules as the control for AI features in Search | honoured |
| Google | `Google-Extended` | control token, no crawler of its own: Gemini training and grounding; "does not impact a site's inclusion in Google Search" | it is a robots.txt token |
| Google | `Google-CloudVertexBot` | Vertex AI Agents for the site owner; "no effect on Google Search" | honoured |
| Microsoft | `Bingbot` | search; the Bing Webmaster Guidelines list "Blocking Bingbot in your robots.txt file" among things to avoid and say Copilot relies on the same crawling and indexing | honoured: "Robots.txt files can be configured to tell Bing crawlers how to interact with your website"; crawl rate set by hour in Bing Webmaster Tools (Crawl control); user agents can be spoofed, check the IP with Verify Bingbot (bing.com/webmasters/help/which-crawlers-does-bing-use-8c184ec0 and the guidelines, pasted by the user on 2026-10-25) |

Consequences for the report:
- Blocking `Google-Extended` does not remove a site from AI Overviews; only Googlebot rules and
  snippet controls (`nosnippet`, `data-nosnippet`, `max-snippet`, `noindex`) do.
- A `Disallow` for a user-triggered fetcher (`ChatGPT-User`, `Perplexity-User`) may not be
  applied by the vendor: report it as a stated preference, not as a block.
- Bing's Copilot controls are meta directives, not a separate token: "NOARCHIVE prevents content
  from being used in Copilot responses and grounding results"; "NOCACHE limits Copilot to using
  only the URL, title, and snippet" (Bing Webmaster Guidelines, 2026-10-25). `ai_access.py`
  reports both per page.

Sources (2026-10-24; Mistral 2026-10-25): developers.openai.com/api/docs/bots; docs.mistral.ai/robots;
support.claude.com/en/articles/8896518; docs.perplexity.ai/guides/bots;
developers.google.com/search/docs/crawling-indexing/google-common-crawlers and
developers.google.com/search/docs/appearance/ai-features;
learn.microsoft.com/en-us/microsoft-365/copilot/manage-public-web-access.
If a page cannot be read at run time, write "not verified today" next to the token.

## Reading robots.txt

1. Fetch `https://<host>/robots.txt` (and the `www` / non-`www` host the site redirects to).
   Note status code and date. A 4xx usually means "no rules"; a 5xx or timeout means "not read".
2. For each token, find the most specific `User-agent` group that matches it; fall back to `*`.
3. Report per token: `allowed`, `disallowed (path)`, `partially disallowed (paths)`, or
   `not mentioned (falls back to *)`.
4. Also note: firewall or CDN bot-blocking cannot be seen in robots.txt. If the user reports it
   or a fetch is refused, say "may be blocked at the server, not visible here".
5. Do not test access by spoofing a vendor's user agent.

## Other access checks (light)

- Key pages readable without JavaScript (open the raw HTML; if the main text is missing, say
  so — the skill cannot tell how each engine renders).
- `noindex` on key pages would also keep them out of search-based answers.
