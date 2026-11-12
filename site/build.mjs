// Builds the SAYA landing page as one self-contained file: node site/build.mjs
//
// page.html holds the page: everything above <!--BODY--> goes in <head>. The build puts the
// Hairline engine (hairline-kernel.js, unchanged) where <!--KERNEL--> is, each figure that exists
// as a module script where <!--FIGURES--> is, and the app screenshot where {{SHOT}} is. It writes
//   index.html          a full document, for GitHub Pages, Vercel or opening from disk
//   index.artifact.html the same page without the document shell, for a claude.ai artifact
import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const read = (f) => readFileSync(join(here, f), "utf8");
const FIGURES = ["shade", "plaza", "sieve", "fork"];

const script = (code, type) => {
  if (/<\/script/i.test(code)) throw new Error("a script contains </script>");
  return `<script${type ? ` type="${type}"` : ""}>\n${code}\n</script>`;
};
const found = FIGURES.filter((f) => existsSync(join(here, f + ".js")));
const shot = "data:image/jpeg;base64," + readFileSync(join(here, "../docs/web-3d.jpg")).toString("base64");

const [head, body] = read("page.html").split("<!--BODY-->");
const fill = (s) => s
  .replace("<!--KERNEL-->", () => script(read("hairline-kernel.js")))
  .replace("<!--FIGURES-->", () => found.map((f) => script(read(f + ".js"), "module")).join("\n"))
  .replaceAll("{{SHOT}}", shot);

writeFileSync(join(here, "index.html"), `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
${head.trim()}
</head>
<body>
${fill(body).trim()}
</body>
</html>
`);
writeFileSync(join(here, "index.artifact.html"), head.trim() + "\n" + fill(body).trim() + "\n");
console.log(`built site/index.html with ${found.length} of ${FIGURES.length} figures: ${found.join(", ")}`);
