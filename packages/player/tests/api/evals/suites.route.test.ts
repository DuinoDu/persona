import { mkdtemp, mkdir, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { NextRequest } from "next/server";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";

const prismaMock = vi.hoisted(() => ({
  evalSuite: {
    create: vi.fn(),
  },
  inferHost: {
    findUnique: vi.fn(),
  },
}));

const remoteCountEvalSuiteCasesMock = vi.hoisted(() => vi.fn());

vi.mock("@/lib/db", () => ({
  prisma: prismaMock,
}));

vi.mock("@ququ/agent/remoteJobs", () => ({
  remoteCountEvalSuiteCases: remoteCountEvalSuiteCasesMock,
}));

type SuitesPostHandler = typeof import("../../../src/app/api/evals/suites/route")["POST"];

let POST: SuitesPostHandler;

const tempDirs: string[] = [];

beforeAll(async () => {
  ({ POST } = await import("../../../src/app/api/evals/suites/route"));
});

afterEach(async () => {
  prismaMock.evalSuite.create.mockReset();
  prismaMock.inferHost.findUnique.mockReset();
  remoteCountEvalSuiteCasesMock.mockReset();

  while (tempDirs.length > 0) {
    const tempDir = tempDirs.pop();
    if (tempDir) {
      await rm(tempDir, { recursive: true, force: true });
    }
  }
});

async function createSuiteDir(caseFiles: Record<string, string>) {
  const root = await mkdtemp(join(tmpdir(), "suites-route-"));
  tempDirs.push(root);

  await writeFile(join(root, "suite.json"), JSON.stringify({ slug: "demo" }));
  await mkdir(join(root, "cases"), { recursive: true });

  for (const [fileName, content] of Object.entries(caseFiles)) {
    await writeFile(join(root, "cases", fileName), content);
  }

  return root;
}

function makeRequest(body: Record<string, unknown>) {
  return new NextRequest("http://localhost/api/evals/suites", {
    method: "POST",
    headers: {
      "content-type": "application/json",
    },
    body: JSON.stringify(body),
  });
}

describe("POST /api/evals/suites", () => {
  it("counts local suite cases from cases/*.jsonl", async () => {
    const sourcePath = await createSuiteDir({
      "a.jsonl": '{"id":1}\n\n{"id":2}\n',
      "b.jsonl": '\n{"id":3}\n',
    });

    prismaMock.evalSuite.create.mockImplementation(async ({ data }) => ({
      id: "suite-local",
      ...data,
    }));

    const response = await POST(
      makeRequest({
        slug: "local-suite",
        title: "Local Suite",
        sourcePath,
      })
    );

    expect(response.status).toBe(200);
    expect(prismaMock.evalSuite.create).toHaveBeenCalledWith(
      expect.objectContaining({
        data: expect.objectContaining({
          caseCount: 3,
          sourcePath,
          slug: "local-suite",
        }),
      })
    );
    await expect(response.json()).resolves.toEqual(
      expect.objectContaining({
        caseCount: 3,
        sourcePath,
      })
    );
  });

  it("falls back to remoteCountEvalSuiteCases when local counting fails", async () => {
    const sourcePath = await createSuiteDir({});

    prismaMock.inferHost.findUnique.mockResolvedValue({
      sshHost: "infer.example.com",
      sshPort: 22,
      sshUser: "runner",
      workspacePath: "/workspace",
    });
    remoteCountEvalSuiteCasesMock.mockResolvedValue(7);
    prismaMock.evalSuite.create.mockImplementation(async ({ data }) => ({
      id: "suite-remote",
      ...data,
    }));

    const response = await POST(
      makeRequest({
        slug: "remote-suite",
        title: "Remote Suite",
        sourcePath,
        inferHostId: "host-1",
      })
    );

    expect(response.status).toBe(200);
    expect(prismaMock.inferHost.findUnique).toHaveBeenCalledWith({
      where: { id: "host-1" },
    });
    expect(remoteCountEvalSuiteCasesMock).toHaveBeenCalledWith({
      host: {
        sshHost: "infer.example.com",
        sshPort: 22,
        sshUser: "runner",
        workspacePath: "/workspace",
      },
      suitePath: sourcePath,
    });
    expect(prismaMock.evalSuite.create).toHaveBeenCalledWith(
      expect.objectContaining({
        data: expect.objectContaining({
          caseCount: 7,
          sourcePath,
          slug: "remote-suite",
        }),
      })
    );
    await expect(response.json()).resolves.toEqual(
      expect.objectContaining({
        caseCount: 7,
        sourcePath,
      })
    );
  });
});
