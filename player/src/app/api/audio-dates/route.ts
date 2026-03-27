import { NextResponse } from "next/server";
import { listAvailableDates } from "@/lib/partIndex";

export const dynamic = "force-dynamic";

export async function GET() {
  return NextResponse.json(
    { items: listAvailableDates() },
    {
      headers: {
        "Cache-Control": "no-store",
      },
    }
  );
}
