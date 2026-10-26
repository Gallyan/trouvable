# Platform sources

Answer engines change how they find, choose and link sources. The rows below are what each
vendor's own pages said when they were read; they are a starting point, not a rule. At run
time, re-open each source URL, compare, and date the reading in the report. A row that no
longer matches the page is dropped, not kept from memory.

## What the vendors state (read on 2026-10-25)

| Platform | Statement (quoted or closely paraphrased) | Source | What it means for a site |
|---|---|---|---|
| Google AI Overviews and AI Mode | To be a supporting link, "a page must be indexed and eligible to be shown in Google Search with a snippet"; "There are no additional technical requirements." | developers.google.com/search/docs/appearance/ai-features (updated 2025-12-10) | Classic indexing and snippet eligibility are the whole entry ticket |
| Google AI Overviews and AI Mode | "There are no additional requirements to appear in AI Overviews or AI Mode, nor other special optimizations necessary"; no need for "new machine readable files, AI text files, or markup", nor "special schema.org structured data". | same | No llms.txt, markup or "AI file" is required by Google for these features |
| Google AI Overviews and AI Mode | Links come from query fan-out: the models "identify more supporting web pages" while the response is generated, showing "a wider and more diverse set of helpful links"; AI Overviews appear only when "additive to classic Search". | same | Pages answering sub-questions of a query can be linked, not only the top result |
| Google AI Overviews and AI Mode | Controls: robots.txt rules for Googlebot govern crawling for Search; `nosnippet`, `data-nosnippet`, `max-snippet` and `noindex` limit what is shown. Appearances are counted in the Search Console Performance report, search type "Web". | same | Snippet controls on key passages reduce what can be quoted; there is no separate AI report |
| Gemini Apps | `Google-Extended` controls whether Google's crawled content is used to train Gemini models and for grounding (content "from the Google Search index to the model at prompt time") in Gemini Apps and Vertex AI; it "does not impact a site's inclusion in Google Search nor is it used as a ranking signal". | developers.google.com/search/docs/crawling-indexing/google-common-crawlers (updated 2026-10-15) | Blocking Google-Extended affects Gemini Apps grounding, not AI Overviews or AI Mode |
| Gemini Apps | "Not all responses include related links or sources"; links "may include content that is related to parts of Gemini's response", including public websites. | support.google.com/gemini/answer/14143489 | A link under a Gemini answer shows related content; the page does not say it is what the answer was built from |
| ChatGPT search | "OAI-SearchBot is used to surface websites in search results in ChatGPT's search features"; sites opted out of it "will not be shown in ChatGPT search answers" but "can still appear as navigational links"; OpenAI recommends allowing it in robots.txt; robots.txt changes take "~24 hours". | developers.openai.com/api/docs/bots | Allowing OAI-SearchBot is the prerequisite; GPTBot (training) is a separate choice |
| ChatGPT search | The former Publishers FAQ address (help.openai.com/en/articles/12627856) redirected on 2026-10-25 to an unrelated page ("ChatGPT Atlas retirement"): no publisher FAQ found at that address. The crawler page above is the only vendor statement read. | — | Do not quote older copies of the FAQ (referral parameter, noindex, Atlas behaviour) as current |
| Perplexity | PerplexityBot "is designed to surface and link websites in search results on Perplexity" and "is not used to crawl content for AI foundation models"; Perplexity-User may visit a page "to help provide an accurate answer and include a link to the page in its response" and "generally ignores robots.txt rules". | docs.perplexity.ai/guides/bots | Allowing PerplexityBot is the prerequisite to be linked |
| Perplexity | How answers choose or rank sources: no official statement found on 2026-10-25 (only third-party articles, which are claims, not vendor statements). | — | Do not present ranking factors for Perplexity as documented |
| Mistral Vibe (formerly Le Chat) | "Le Chat has become Vibe" (2026-08-12); `MistralAI-User` "may visit a web page to help answer and include a link to the source in its response"; `MistralAI-Index` crawls for Mistral search; web answers show "Inline links pointing back to the original sources" and a Sources button | help.mistral.ai/en/articles/682992; docs.mistral.ai/robots; docs.mistral.ai/vibe/work/web-search-open-url | Say Vibe, not Le Chat; allowing MistralAI-Index and MistralAI-User is the prerequisite to be linked; how sources are chosen is not stated |
| Microsoft Copilot | When web search is enabled, Copilot "may fetch information from the Bing search service"; it sends Bing a generated query of "a few words informed by the user's prompt", and Copilot Chat shows those queries in its citation section. | learn.microsoft.com/en-us/microsoft-365/copilot/manage-public-web-access (updated 2026-08-18) | Being found by Bing for short queries on the topic is the route into Copilot answers |
| Microsoft Copilot | The guidelines cover "Bing search experiences, Copilot, and grounding API results"; Copilot "rel[ies] on the same core crawling, indexing, and ranking foundation as traditional search". | Bing Webmaster Guidelines (bing.com/webmasters/help/webmasters-guidelines-30fba23a), pasted by the user from a browser on 2026-10-25 | Classic Bing indexing is the entry ticket; Bing Webmaster Tools and IndexNow matter here |
| Microsoft Copilot | Controls: `NOINDEX` keeps a URL out of "Bing search, Copilot experiences, or grounding API results"; `NOSNIPPET` and `DATA-NOSNIPPET` "may limit Copilot citation quality"; "NOARCHIVE prevents content from being used in Copilot responses and grounding results"; "NOCACHE limits Copilot to using only the URL, title, and snippet". | same | `noarchive` or `nocache` on a key page is a Copilot blocker to report |
| Microsoft Copilot | Content: URLs "are more likely to be selected for grounding queries and citations when content stands on its own": explicit facts, key information near the top, one topic per URL, clear and consistent entity names; "GEO does not guarantee grounding or citations". | same | Matches the passage checks; no promise of citation |
| Microsoft Copilot | Abuse: "Attempts to add content designed to manipulate or interfere with language models used by Bing or Copilot may result in reduced visibility or removal". | same | Hidden instructions for AI are a risk, never a tactic |

## How to write a platform row in a report

| Platform | Statement (quoted or closely paraphrased) | Source URL | Read on | What it means for this site |
|---|---|---|---|---|

- One row per statement. A blog post, a study or a forum thread about a platform is not the
  platform's statement: cite it separately, as a claim, with its date.
- When the vendor says nothing on a point, write "no official statement found on {date}".
- A page that cannot be read (JavaScript, 403) is "not read", never "says nothing".
- Never turn a statement into a promise: "allowing the agent makes the page eligible" is not
  "the page will be cited".
