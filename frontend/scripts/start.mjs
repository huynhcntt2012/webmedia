import { cpSync, existsSync } from "node:fs";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";

const root = process.cwd();
const standalone = resolve(root, ".next/standalone");
if (!existsSync(resolve(standalone, "server.js"))) {
  throw new Error("Build the frontend before starting the standalone server.");
}
cpSync(resolve(root, ".next/static"), resolve(standalone, ".next/static"), {recursive:true});
cpSync(resolve(root, "public"), resolve(standalone, "public"), {recursive:true});
process.env.HOSTNAME = "127.0.0.1";
await import(pathToFileURL(resolve(standalone, "server.js")).href);
