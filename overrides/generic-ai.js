"use strict";
// PATCHED COPY — supports splitting chat and embedding providers.
//
// Original behaviour (unchanged when EMBEDDING_PROVIDER is unset):
//   - getModel() and getEmbeddingModel() both use `defaultProvider`
//     (ollama if OLLAMA_BASE_URL is set, otherwise openai).
//
// New behaviour (when EMBEDDING_PROVIDER is set to one of the keys in
// providerList, e.g. "deepinfra"):
//   - getModel() still uses defaultProvider for chat.
//   - getEmbeddingModel() uses the EMBEDDING_PROVIDER provider for
//     embeddings, with an optional EMBEDDING_BASE_URL override so an
//     OpenAI-compatible base (DeepInfra's `/v1/openai`) can be used
//     without disturbing OPENAI_BASE_URL.
//
// This lets the host run GLM-5.2 chat through Z.AI while routing
// embeddings to DeepInfra (Qwen3-Embedding-8B, BGE, etc.).
Object.defineProperty(exports, "__esModule", { value: true });
exports.getModel = getModel;
exports.getEmbeddingModel = getEmbeddingModel;
const openai_1 = require("@ai-sdk/openai");
const config_1 = require("../config");
const ollama_ai_provider_v2_1 = require("ollama-ai-provider-v2");
const anthropic_1 = require("@ai-sdk/anthropic");
const groq_1 = require("@ai-sdk/groq");
const google_1 = require("@ai-sdk/google");
const ai_sdk_provider_1 = require("@openrouter/ai-sdk-provider");
const fireworks_1 = require("@ai-sdk/fireworks");
const deepinfra_1 = require("@ai-sdk/deepinfra");
const google_vertex_1 = require("@ai-sdk/google-vertex");
const ai_1 = require("ai");
const defaultProvider = config_1.config.OLLAMA_BASE_URL ? "ollama" : "openai";
// Embeddings may use a different provider than chat. Default is whatever
// chat uses; set EMBEDDING_PROVIDER in env to override (e.g. "deepinfra").
const embeddingProvider = process.env.EMBEDDING_PROVIDER || defaultProvider;
// When the embedding provider is the OpenAI-shaped one and the env has
// EMBEDDING_BASE_URL set, build a dedicated provider client pointed at it
// so DeepInfra's OpenAI-compatible endpoint can be used without touching
// OPENAI_BASE_URL.
const embeddedOpenAIProvider = process.env.DEEPINFRA_BASE_URL
    ? (0, openai_1.createOpenAI)({
        apiKey: config_1.config.DEEPINFRA_API_KEY,
        baseURL: process.env.DEEPINFRA_BASE_URL,
    })
    : null;
const providerList = {
    openai: (0, openai_1.createOpenAI)({
        apiKey: config_1.config.OPENAI_API_KEY,
        baseURL: config_1.config.OPENAI_BASE_URL,
    }), //OPENAI_API_KEY
    ollama: (0, ollama_ai_provider_v2_1.createOllama)({
        baseURL: config_1.config.OLLAMA_BASE_URL,
    }),
    anthropic: anthropic_1.anthropic, //ANTHROPIC_API_KEY
    groq: //ANTHROPIC_API_KEY
    groq_1.groq, //GROQ_API_KEY
    google: //GROQ_API_KEY
    google_1.google, //GOOGLE_GENERATIVE_AI_API_KEY
    openrouter: (0, ai_sdk_provider_1.createOpenRouter)({
        apiKey: config_1.config.OPENROUTER_API_KEY,
    }),
    fireworks: fireworks_1.fireworks, //FIREWORKS_API_KEY
    deepinfra: //FIREWORKS_API_KEY
    process.env.DEEPINFRA_BASE_URL && embeddedOpenAIProvider
        ? embeddedOpenAIProvider // use EMBEDDING_BASE_URL when configured
        : deepinfra_1.deepinfra, //DEEPINFRA_API_KEY
    vertex: (0, google_vertex_1.createVertex)({
        project: "firecrawl",
        //https://github.com/vercel/ai/issues/6644 bug
        baseURL: "https://aiplatform.googleapis.com/v1/projects/firecrawl/locations/global/publishers/google",
        location: "global",
        googleAuthOptions: config_1.config.VERTEX_CREDENTIALS
            ? {
                credentials: JSON.parse(atob(config_1.config.VERTEX_CREDENTIALS)),
            }
            : {
                keyFile: "./gke-key.json",
            },
    }),
};
// Middleware that makes OpenAI-compatible providers (which only support
// `response_format: {type: "json_object"}`, not the OpenAI-specific
// `{type: "json_schema", ...}`) cooperate with ai-sdk's `generateObject` /
// `generateText` schema-driven calls.
//
// Two problems this addresses, observed against Z.AI's GLM-5.2:
//   1. The provider ignores the strict `json_schema` mode and invents its
//      own JSON shape. Fix: inject a strict system message that names the
//      EXACT keys the schema requires (extracted from the call's prompt).
//   2. The provider wraps JSON in ```json ... ``` markdown fences. The
//      ai-sdk JSON parser chokes on the fences. Fix: post-process the raw
//      text response to strip code fences before parsing.
//
// Safe to apply unconditionally: if the model already emits clean JSON
// matching the schema, the preprocessing is a no-op.
function jsonSafetyMiddleware() {
    return {
        specificationVersion: "v3",
        transformParams: async ({ params }) => {
            // Only intervene when ai-sdk is asking for JSON-shaped output
            // (responseFormat present and json-shaped).
            const wantsJson = params.responseFormat?.type === "json";
            if (!wantsJson)
                return params;
            // Find the schema shape so we can tell the model the exact keys.
            // ai-sdk encodes the requested JSON schema on params.responseFormat
            // when `json_schema`/`json` is requested.
            const schemaShape = params.responseFormat?.schema;
            let keyHint = "";
            if (schemaShape && schemaShape.properties) {
                const keys = Object.keys(schemaShape.properties);
                keyHint = `\n\nCRITICAL: Return ONLY a JSON object with EXACTLY these keys: ${JSON.stringify(keys)}. No markdown code fences. No prose. Only raw JSON.`;
            }
            else {
                keyHint = `\n\nCRITICAL: Return ONLY raw JSON. No markdown code fences. No prose.`;
            }
            // Prefer appending to an existing system message so we don't break
            // any required system framing the caller provided.
            const prompt = params.prompt;
            const newPrompt = Array.isArray(prompt)
                ? prompt.map((msg, i) => i === 0 && msg.role === "system"
                    ? { ...msg, content: `${msg.content}${keyHint}` }
                    : msg)
                : prompt;
            // Also explicitly downgrade to json_object (the only mode Z.AI
            // actually supports). ai-sdk may have sent json_schema; some
            // providers 400 on unsupported response_format variants, others
            // (like Z.AI) silently fall back to freeform.
            const newResponseFormat = { type: "json" };
            return {
                ...params,
                prompt: newPrompt,
                responseFormat: newResponseFormat,
            };
        },
        wrapGenerate: async ({ doGenerate }) => {
            const result = await doGenerate();
            // Strip ```json ... ``` fences from the raw text so ai-sdk's JSON
            // parser succeeds. content is an array of parts (ai-sdk v3+).
            if (Array.isArray(result?.content)) {
                let mutated = false;
                const newContent = result.content.map((part) => {
                    if (typeof part?.text === "string" && /^```(?:json)?\s*/m.test(part.text)) {
                        mutated = true;
                        return {
                            ...part,
                            text: part.text
                                .replace(/^```(?:json)?\s*/g, "")
                                .replace(/```\s*$/g, "")
                                .trim(),
                        };
                    }
                    return part;
                });
                if (mutated)
                    return { ...result, content: newContent };
            }
            return result;
        },
    };
}
// Memoize wrapped models so repeated getModel calls don't re-wrap.
const wrappedModelCache = new Map();
function wrapIfOpenAICompatible(model) {
    // The ai-sdk `createOpenAI(...)` provider returns models whose config
    // reports provider as "openai.chat" or "openai.responses". Our patched
    // deepinfra entry uses the same createOpenAI factory under the hood when
    // DEEPINFRA_BASE_URL is set. We detect via model.config.provider.
    const modelId = model?.modelId ?? "";
    const providerTag = model?.config?.provider ?? "";
    if (!providerTag.startsWith("openai"))
        return model;
    const cacheKey = `${providerTag}:${modelId}`;
    if (wrappedModelCache.has(cacheKey))
        return wrappedModelCache.get(cacheKey);
    const wrapped = (0, ai_1.wrapLanguageModel)({
        model,
        middleware: jsonSafetyMiddleware(),
    });
    wrappedModelCache.set(cacheKey, wrapped);
    return wrapped;
}
function getModel(name, provider = defaultProvider) {
    if (name === "gemini-2.5-pro") {
        name = "gemini-2.5-pro";
    }
    const modelName = config_1.config.MODEL_NAME || name;
    // When the OpenAI provider is pointed at an OpenAI-compatible endpoint that
    // does NOT implement the Responses API (e.g. Z.AI, DeepInfra, OpenRouter),
    // we must force the Chat Completions sub-provider explicitly. The ai-sdk
    // openai provider otherwise defaults known model names (gpt-4.1, gpt-4o, …)
    // to OpenAIResponsesLanguageModel, which POSTs to /responses and 404s on
    // every compliant-but-non-OpenAI base URL.
    if (provider === "openai") {
        const unwrapped = providerList.openai.chat(modelName);
        return wrapIfOpenAICompatible(unwrapped);
    }
    return providerList[provider](modelName);
}
function getEmbeddingModel(name, provider = embeddingProvider) {
    return config_1.config.MODEL_EMBEDDING_NAME
        ? providerList[provider].embedding(config_1.config.MODEL_EMBEDDING_NAME)
        : providerList[provider].embedding(name);
}
//# sourceMappingURL=generic-ai.js.map
