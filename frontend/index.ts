import index from "./index.html";

const BACKEND_URL = process.env.BACKEND_URL || "http://localhost:8000";
const PORT = Number(process.env.PORT || 3000);

const server = Bun.serve({
  port: PORT,

  routes: {
    // Proxy API requests to FastAPI backend
    "/api/*": async (req) => {
      const url = new URL(req.url);
      const backendUrl = `${BACKEND_URL}${url.pathname}${url.search}`;

      const headers = new Headers(req.headers);
      // Forward the cookie header for session authentication
      const cookie = req.headers.get("cookie");
      if (cookie) {
        headers.set("cookie", cookie);
      }

      try {
        const backendRes = await fetch(backendUrl, {
          method: req.method,
          headers,
          body: req.method !== "GET" && req.method !== "HEAD" ? await req.text() : undefined,
          signal: AbortSignal.timeout(30_000),
        });

        // Create response with same status and headers
        const responseHeaders = new Headers(backendRes.headers);

        return new Response(backendRes.body, {
          status: backendRes.status,
          statusText: backendRes.statusText,
          headers: responseHeaders,
        });
      } catch (error) {
        console.error("Backend proxy error:", error);
        return Response.json(
          { error: "Backend unavailable" },
          { status: 502 }
        );
      }
    },

    // Serve HTML for all other routes (SPA)
    "/*": index,
  },

  development: process.env.NODE_ENV !== "production" && {
    hmr: true,
    console: true,
  },
});

console.log(`Frontend server running at ${server.url}`);
console.log(`Proxying API requests to ${BACKEND_URL}`);
