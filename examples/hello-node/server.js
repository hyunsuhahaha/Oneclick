// Dockerfile 없는 Node 앱: oneclick이 package.json을 보고 Dockerfile을 만든다.
const http = require("http");
const os = require("os");

const port = process.env.PORT || 8080;
const started = new Date().toISOString();

http.createServer((req, res) => {
  if (req.url === "/healthz") {
    res.writeHead(200).end("ok");
    return;
  }
  res.writeHead(200, { "Content-Type": "text/html; charset=utf-8" });
  res.end(`<h1>hello-node</h1><p>host: ${os.hostname()}</p><p>started: ${started}</p>`);
}).listen(port, () => console.log(`listening on ${port}`));
