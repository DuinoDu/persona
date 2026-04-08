import path from "node:path";
import type { NextConfig } from "next";

const workspaceRoot = path.resolve(__dirname, "../..");
const agentSrcRoot = path.resolve(__dirname, "../agent/src");
const processSrcRoot = path.resolve(__dirname, "../process/src");
const agentEntries = [
  "evalArtifacts",
  "inferenceTrace",
  "liveSessionRuntime",
  "personaContextBuilder",
  "personaExport",
  "personaRuntime",
  "remoteJobs",
  "remoteSse",
] as const;
const agentWebpackAliases = Object.fromEntries(
  agentEntries.map((name) => [`@ququ/agent/${name}`, path.join(agentSrcRoot, `${name}.ts`)])
);
const agentTurboAliases = Object.fromEntries(
  [
    ["@ququ/agent", "./node_modules/@ququ/agent/src/index.ts"],
    ["@ququ/process", "./node_modules/@ququ/process/src/index.ts"],
    ...agentEntries.map((name) => [
      `@ququ/agent/${name}`,
      `./node_modules/@ququ/agent/src/${name}.ts`,
    ]),
  ]
);

const nextConfig: NextConfig = {
  turbopack: {
    root: workspaceRoot,
    resolveAlias: agentTurboAliases,
  },
  allowedDevOrigins: ["http://100.72.208.174"],
  transpilePackages: ["@ququ/agent", "@ququ/process"],
  experimental: {
    externalDir: true,
  },
  webpack(config) {
    config.resolve = config.resolve || {};
    config.resolve.alias = {
      ...(config.resolve.alias || {}),
      "@ququ/agent": path.join(agentSrcRoot, "index.ts"),
      "@ququ/process": path.join(processSrcRoot, "index.ts"),
      ...agentWebpackAliases,
    };
    return config;
  },
};

export default nextConfig;
