// Configuracion OAuth de cada red. Las llaves van como variables de entorno en Vercel.
export const REDES = {
  youtube: {
    autorizar: (r) =>
      "https://accounts.google.com/o/oauth2/v2/auth?" +
      new URLSearchParams({
        client_id: process.env.GOOGLE_CLIENT_ID, redirect_uri: r.redirect, response_type: "code",
        scope: "https://www.googleapis.com/auth/youtube.upload https://www.googleapis.com/auth/youtube.readonly",
        access_type: "offline", prompt: "consent", state: r.state,
      }),
    async canjear(code, redirect) {
      const t = await fetch("https://oauth2.googleapis.com/token", {
        method: "POST", headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: new URLSearchParams({
          code, client_id: process.env.GOOGLE_CLIENT_ID, client_secret: process.env.GOOGLE_CLIENT_SECRET,
          redirect_uri: redirect, grant_type: "authorization_code",
        }),
      }).then((x) => x.json());
      if (!t.refresh_token) throw new Error("Google no entrego acceso permanente: " + JSON.stringify(t));
      const c = await fetch("https://www.googleapis.com/youtube/v3/channels?part=snippet&mine=true", {
        headers: { Authorization: `Bearer ${t.access_token}` },
      }).then((x) => x.json());
      return {
        cuenta: c.items?.[0]?.snippet?.title || "canal de YouTube",
        datos: { access_token: t.access_token, refresh_token: t.refresh_token, expira: Date.now() / 1000 + (t.expires_in || 3600) },
      };
    },
  },
  tiktok: {
    autorizar: (r) =>
      "https://www.tiktok.com/v2/auth/authorize/?" +
      new URLSearchParams({
        client_key: process.env.TIKTOK_CLIENT_KEY, redirect_uri: r.redirect, response_type: "code",
        scope: "user.info.basic,video.upload,video.publish", state: r.state,
      }),
    async canjear(code, redirect) {
      const t = await fetch("https://open.tiktokapis.com/v2/oauth/token/", {
        method: "POST", headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: new URLSearchParams({
          client_key: process.env.TIKTOK_CLIENT_KEY, client_secret: process.env.TIKTOK_CLIENT_SECRET,
          code, grant_type: "authorization_code", redirect_uri: redirect,
        }),
      }).then((x) => x.json());
      if (!t.access_token) throw new Error("TikTok no acepto: " + JSON.stringify(t));
      const u = await fetch("https://open.tiktokapis.com/v2/user/info/?fields=display_name", {
        headers: { Authorization: `Bearer ${t.access_token}` },
      }).then((x) => x.json());
      return {
        cuenta: u.data?.user?.display_name || "cuenta de TikTok",
        datos: { access_token: t.access_token, refresh_token: t.refresh_token, open_id: t.open_id, expira: Date.now() / 1000 + (t.expires_in || 86400) },
      };
    },
  },
  instagram: {
    autorizar: (r) =>
      "https://www.instagram.com/oauth/authorize?" +
      new URLSearchParams({
        client_id: process.env.INSTAGRAM_APP_ID, redirect_uri: r.redirect, response_type: "code",
        scope: "instagram_business_basic,instagram_business_content_publish", state: r.state,
      }),
    async canjear(code, redirect) {
      const corto = await fetch("https://api.instagram.com/oauth/access_token", {
        method: "POST", headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: new URLSearchParams({
          client_id: process.env.INSTAGRAM_APP_ID, client_secret: process.env.INSTAGRAM_APP_SECRET,
          grant_type: "authorization_code", redirect_uri: redirect, code,
        }),
      }).then((x) => x.json());
      if (!corto.access_token) throw new Error("Instagram no acepto: " + JSON.stringify(corto));
      const largo = await fetch("https://graph.instagram.com/access_token?" + new URLSearchParams({
        grant_type: "ig_exchange_token", client_secret: process.env.INSTAGRAM_APP_SECRET, access_token: corto.access_token,
      })).then((x) => x.json());
      const tok = largo.access_token || corto.access_token;
      const me = await fetch(`https://graph.instagram.com/v21.0/me?fields=user_id,username&access_token=${tok}`).then((x) => x.json());
      return {
        cuenta: me.username ? "@" + me.username : "cuenta de Instagram",
        datos: { access_token: tok, ig_user_id: me.user_id || corto.user_id, renovado: Date.now() / 1000 },
      };
    },
  },
};

export function redirectDe(req, red) {
  const base = process.env.NEXT_PUBLIC_SITE_URL || new URL(req.url).origin;
  return `${base}/api/oauth/${red}/callback`;
}
