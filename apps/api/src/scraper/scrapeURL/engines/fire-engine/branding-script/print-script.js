#!/usr/bin/env node


const esbuild = require("esbuild");
const path = require("path");

const entryPoint = path.join(__dirname, "index.ts");

const result = esbuild.buildSync({
  entryPoints: [entryPoint],
  bundle: true,
  minify: false, 
  format: "iife",
  globalName: "__extractBrandDesign",
  target: ["es2020"],
  write: false,
});

const bundledCode = result.outputFiles[0].text;


const script = `(function __extractBrandDesign() {
${bundledCode}
return __extractBrandDesign.extractBrandDesign();
})();`;

process.stdout.write(script);
