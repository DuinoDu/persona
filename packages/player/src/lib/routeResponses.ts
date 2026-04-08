import { NextResponse } from "next/server";

export interface ServiceRouteResult {
  status: number;
  body: unknown;
}

export function serviceJson(
  result: ServiceRouteResult,
  options?: {
    noStore?: boolean;
    headers?: HeadersInit;
  }
) {
  const headers = new Headers(options?.headers);
  if (options?.noStore) {
    headers.set("Cache-Control", "no-store");
  }
  return NextResponse.json(result.body, {
    status: result.status,
    headers,
  });
}

export function jsonNoStore(body: unknown, status = 200, headers?: HeadersInit) {
  return NextResponse.json(body, {
    status,
    headers: {
      "Cache-Control": "no-store",
      ...(headers || {}),
    },
  });
}

function encodeSsePayload(payload: unknown) {
  return `data: ${JSON.stringify(payload)}\n\n`;
}

export function sseResponse(streamSource: AsyncIterable<unknown>) {
  const encoder = new TextEncoder();
  const stream = new ReadableStream<Uint8Array>({
    async start(controller) {
      try {
        for await (const event of streamSource) {
          controller.enqueue(encoder.encode(encodeSsePayload(event)));
        }
      } finally {
        controller.close();
      }
    },
  });

  return new Response(stream, {
    headers: {
      "Content-Type": "text/event-stream; charset=utf-8",
      "Cache-Control": "no-store",
      Connection: "keep-alive",
    },
  });
}
