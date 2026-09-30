import { generateObject, generateText, tool } from "ai";
import type { GenerateObjectResult } from "ai";
import { config } from "../config";

/**
 * Structured generation that works on OpenAI-compatible third-party endpoints.
 *
 * The AI SDK asks the provider for a JSON-schema response via
 * `response_format: {type: "json_schema"}`. Endpoints such as Z.ai'"'"'s Coding Plan
 * ignore that field and answer in prose, so schema validation fails and the call
 * throws `AI_NoObjectGeneratedError`. Those same endpoints do honour tool
 * calling, so this helper forces a single tool call and reads its already-parsed
 * arguments instead.
 *
 * Providers that support `response_format` keep the original `generateObject`
 * path, so behaviour is unchanged for OpenAI, Anthropic, Google and the rest.
 */
export async function generateStructuredObject(
  options: Parameters<typeof generateObject>[0],
): Promise<GenerateObjectResult<any>> {
  const model = options.model as any;
  const schema = (options as any).schema;

  const useToolCall =
    !!schema && model?.provider === "openai.chat" && !!config.OPENAI_BASE_URL;

  if (!useToolCall) {
    return await generateObject(options);
  }

  const hasMessages = Array.isArray((options as any).messages);

  const { text, toolCalls, usage, finishReason } = await generateText({
    model: options.model,
    ...(hasMessages
      ? { messages: (options as any).messages }
      : { prompt: (options as any).prompt, system: (options as any).system }),
    ...((options as any).temperature !== undefined
      ? { temperature: (options as any).temperature }
      : {}),
    tools: {
      extract_data: tool({
        description:
          "Return the structured data as a single object. Call this exactly once with every requested field.",
        inputSchema: schema,
      }),
    },
    toolChoice: { type: "tool", toolName: "extract_data" },
    providerOptions: (options as any).providerOptions,
    experimental_telemetry: (options as any).experimental_telemetry,
  });

  const call = toolCalls.find((c) => c.toolName === "extract_data");
  if (!call) {
    throw new Error(
      `Structured generation produced no extract_data tool call${text ? `: ${text.slice(0, 200)}` : ""}`,
    );
  }

  // The tool path has no request/response envelope, so the fields callers read
  // are populated and the remainder are covered by the cast.
  return {
    object: (call as any).input,
    reasoning: undefined,
    finishReason,
    usage,
    warnings: undefined,
  } as unknown as GenerateObjectResult<any>;
}
