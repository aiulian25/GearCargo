try {
  self["workbox:core:7.3.0"] && _();
} catch {
}
const he = (s, ...e) => {
  let t = s;
  return e.length > 0 && (t += ` :: ${JSON.stringify(e)}`), t;
}, le = he;
class l extends Error {
  /**
   *
   * @param {string} errorCode The error code that
   * identifies this particular error.
   * @param {Object=} details Any relevant arguments
   * that will help developers identify issues should
   * be added as a key on the context object.
   */
  constructor(e, t) {
    const n = le(e, t);
    super(n), this.name = e, this.details = t;
  }
}
const p = {
  googleAnalytics: "googleAnalytics",
  precache: "precache-v2",
  prefix: "workbox",
  runtime: "runtime",
  suffix: typeof registration < "u" ? registration.scope : ""
}, I = (s) => [p.prefix, s, p.suffix].filter((e) => e && e.length > 0).join("-"), ue = (s) => {
  for (const e of Object.keys(p))
    s(e);
}, D = {
  updateDetails: (s) => {
    ue((e) => {
      typeof s[e] == "string" && (p[e] = s[e]);
    });
  },
  getGoogleAnalyticsName: (s) => s || I(p.googleAnalytics),
  getPrecacheName: (s) => s || I(p.precache),
  getPrefix: () => p.prefix,
  getRuntimeName: (s) => s || I(p.runtime),
  getSuffix: () => p.suffix
};
function Q(s, e) {
  const t = e();
  return s.waitUntil(t), t;
}
try {
  self["workbox:precaching:7.3.0"] && _();
} catch {
}
const de = "__WB_REVISION__";
function fe(s) {
  if (!s)
    throw new l("add-to-cache-list-unexpected-type", { entry: s });
  if (typeof s == "string") {
    const r = new URL(s, location.href);
    return {
      cacheKey: r.href,
      url: r.href
    };
  }
  const { revision: e, url: t } = s;
  if (!t)
    throw new l("add-to-cache-list-unexpected-type", { entry: s });
  if (!e) {
    const r = new URL(t, location.href);
    return {
      cacheKey: r.href,
      url: r.href
    };
  }
  const n = new URL(t, location.href), a = new URL(t, location.href);
  return n.searchParams.set(de, e), {
    cacheKey: n.href,
    url: a.href
  };
}
class pe {
  constructor() {
    this.updatedURLs = [], this.notUpdatedURLs = [], this.handlerWillStart = async ({ request: e, state: t }) => {
      t && (t.originalRequest = e);
    }, this.cachedResponseWillBeUsed = async ({ event: e, state: t, cachedResponse: n }) => {
      if (e.type === "install" && t && t.originalRequest && t.originalRequest instanceof Request) {
        const a = t.originalRequest.url;
        n ? this.notUpdatedURLs.push(a) : this.updatedURLs.push(a);
      }
      return n;
    };
  }
}
class ge {
  constructor({ precacheController: e }) {
    this.cacheKeyWillBeUsed = async ({ request: t, params: n }) => {
      const a = (n == null ? void 0 : n.cacheKey) || this._precacheController.getCacheKeyForURL(t.url);
      return a ? new Request(a, { headers: t.headers }) : t;
    }, this._precacheController = e;
  }
}
let b;
function me() {
  if (b === void 0) {
    const s = new Response("");
    if ("body" in s)
      try {
        new Response(s.body), b = !0;
      } catch {
        b = !1;
      }
    b = !1;
  }
  return b;
}
async function ye(s, e) {
  let t = null;
  if (s.url && (t = new URL(s.url).origin), t !== self.location.origin)
    throw new l("cross-origin-copy-response", { origin: t });
  const n = s.clone(), r = {
    headers: new Headers(n.headers),
    status: n.status,
    statusText: n.statusText
  }, i = me() ? n.body : await n.blob();
  return new Response(i, r);
}
const we = (s) => new URL(String(s), location.href).href.replace(new RegExp(`^${location.origin}`), "");
function V(s, e) {
  const t = new URL(s);
  for (const n of e)
    t.searchParams.delete(n);
  return t.href;
}
async function _e(s, e, t, n) {
  const a = V(e.url, t);
  if (e.url === a)
    return s.match(e, n);
  const r = Object.assign(Object.assign({}, n), { ignoreSearch: !0 }), i = await s.keys(e, r);
  for (const o of i) {
    const c = V(o.url, t);
    if (a === c)
      return s.match(o, n);
  }
}
class be {
  /**
   * Creates a promise and exposes its resolve and reject functions as methods.
   */
  constructor() {
    this.promise = new Promise((e, t) => {
      this.resolve = e, this.reject = t;
    });
  }
}
const ee = /* @__PURE__ */ new Set();
async function Re() {
  for (const s of ee)
    await s();
}
function te(s) {
  return new Promise((e) => setTimeout(e, s));
}
try {
  self["workbox:strategies:7.3.0"] && _();
} catch {
}
function k(s) {
  return typeof s == "string" ? new Request(s) : s;
}
class Ee {
  /**
   * Creates a new instance associated with the passed strategy and event
   * that's handling the request.
   *
   * The constructor also initializes the state that will be passed to each of
   * the plugins handling this request.
   *
   * @param {workbox-strategies.Strategy} strategy
   * @param {Object} options
   * @param {Request|string} options.request A request to run this strategy for.
   * @param {ExtendableEvent} options.event The event associated with the
   *     request.
   * @param {URL} [options.url]
   * @param {*} [options.params] The return value from the
   *     {@link workbox-routing~matchCallback} (if applicable).
   */
  constructor(e, t) {
    this._cacheKeys = {}, Object.assign(this, t), this.event = t.event, this._strategy = e, this._handlerDeferred = new be(), this._extendLifetimePromises = [], this._plugins = [...e.plugins], this._pluginStateMap = /* @__PURE__ */ new Map();
    for (const n of this._plugins)
      this._pluginStateMap.set(n, {});
    this.event.waitUntil(this._handlerDeferred.promise);
  }
  /**
   * Fetches a given request (and invokes any applicable plugin callback
   * methods) using the `fetchOptions` (for non-navigation requests) and
   * `plugins` defined on the `Strategy` object.
   *
   * The following plugin lifecycle methods are invoked when using this method:
   * - `requestWillFetch()`
   * - `fetchDidSucceed()`
   * - `fetchDidFail()`
   *
   * @param {Request|string} input The URL or request to fetch.
   * @return {Promise<Response>}
   */
  async fetch(e) {
    const { event: t } = this;
    let n = k(e);
    if (n.mode === "navigate" && t instanceof FetchEvent && t.preloadResponse) {
      const i = await t.preloadResponse;
      if (i)
        return i;
    }
    const a = this.hasCallback("fetchDidFail") ? n.clone() : null;
    try {
      for (const i of this.iterateCallbacks("requestWillFetch"))
        n = await i({ request: n.clone(), event: t });
    } catch (i) {
      if (i instanceof Error)
        throw new l("plugin-error-request-will-fetch", {
          thrownErrorMessage: i.message
        });
    }
    const r = n.clone();
    try {
      let i;
      i = await fetch(n, n.mode === "navigate" ? void 0 : this._strategy.fetchOptions);
      for (const o of this.iterateCallbacks("fetchDidSucceed"))
        i = await o({
          event: t,
          request: r,
          response: i
        });
      return i;
    } catch (i) {
      throw a && await this.runCallbacks("fetchDidFail", {
        error: i,
        event: t,
        originalRequest: a.clone(),
        request: r.clone()
      }), i;
    }
  }
  /**
   * Calls `this.fetch()` and (in the background) runs `this.cachePut()` on
   * the response generated by `this.fetch()`.
   *
   * The call to `this.cachePut()` automatically invokes `this.waitUntil()`,
   * so you do not have to manually call `waitUntil()` on the event.
   *
   * @param {Request|string} input The request or URL to fetch and cache.
   * @return {Promise<Response>}
   */
  async fetchAndCachePut(e) {
    const t = await this.fetch(e), n = t.clone();
    return this.waitUntil(this.cachePut(e, n)), t;
  }
  /**
   * Matches a request from the cache (and invokes any applicable plugin
   * callback methods) using the `cacheName`, `matchOptions`, and `plugins`
   * defined on the strategy object.
   *
   * The following plugin lifecycle methods are invoked when using this method:
   * - cacheKeyWillBeUsed()
   * - cachedResponseWillBeUsed()
   *
   * @param {Request|string} key The Request or URL to use as the cache key.
   * @return {Promise<Response|undefined>} A matching response, if found.
   */
  async cacheMatch(e) {
    const t = k(e);
    let n;
    const { cacheName: a, matchOptions: r } = this._strategy, i = await this.getCacheKey(t, "read"), o = Object.assign(Object.assign({}, r), { cacheName: a });
    n = await caches.match(i, o);
    for (const c of this.iterateCallbacks("cachedResponseWillBeUsed"))
      n = await c({
        cacheName: a,
        matchOptions: r,
        cachedResponse: n,
        request: i,
        event: this.event
      }) || void 0;
    return n;
  }
  /**
   * Puts a request/response pair in the cache (and invokes any applicable
   * plugin callback methods) using the `cacheName` and `plugins` defined on
   * the strategy object.
   *
   * The following plugin lifecycle methods are invoked when using this method:
   * - cacheKeyWillBeUsed()
   * - cacheWillUpdate()
   * - cacheDidUpdate()
   *
   * @param {Request|string} key The request or URL to use as the cache key.
   * @param {Response} response The response to cache.
   * @return {Promise<boolean>} `false` if a cacheWillUpdate caused the response
   * not be cached, and `true` otherwise.
   */
  async cachePut(e, t) {
    const n = k(e);
    await te(0);
    const a = await this.getCacheKey(n, "write");
    if (!t)
      throw new l("cache-put-with-no-response", {
        url: we(a.url)
      });
    const r = await this._ensureResponseSafeToCache(t);
    if (!r)
      return !1;
    const { cacheName: i, matchOptions: o } = this._strategy, c = await self.caches.open(i), h = this.hasCallback("cacheDidUpdate"), w = h ? await _e(
      // TODO(philipwalton): the `__WB_REVISION__` param is a precaching
      // feature. Consider into ways to only add this behavior if using
      // precaching.
      c,
      a.clone(),
      ["__WB_REVISION__"],
      o
    ) : null;
    try {
      await c.put(a, h ? r.clone() : r);
    } catch (d) {
      if (d instanceof Error)
        throw d.name === "QuotaExceededError" && await Re(), d;
    }
    for (const d of this.iterateCallbacks("cacheDidUpdate"))
      await d({
        cacheName: i,
        oldResponse: w,
        newResponse: r.clone(),
        request: a,
        event: this.event
      });
    return !0;
  }
  /**
   * Checks the list of plugins for the `cacheKeyWillBeUsed` callback, and
   * executes any of those callbacks found in sequence. The final `Request`
   * object returned by the last plugin is treated as the cache key for cache
   * reads and/or writes. If no `cacheKeyWillBeUsed` plugin callbacks have
   * been registered, the passed request is returned unmodified
   *
   * @param {Request} request
   * @param {string} mode
   * @return {Promise<Request>}
   */
  async getCacheKey(e, t) {
    const n = `${e.url} | ${t}`;
    if (!this._cacheKeys[n]) {
      let a = e;
      for (const r of this.iterateCallbacks("cacheKeyWillBeUsed"))
        a = k(await r({
          mode: t,
          request: a,
          event: this.event,
          // params has a type any can't change right now.
          params: this.params
          // eslint-disable-line
        }));
      this._cacheKeys[n] = a;
    }
    return this._cacheKeys[n];
  }
  /**
   * Returns true if the strategy has at least one plugin with the given
   * callback.
   *
   * @param {string} name The name of the callback to check for.
   * @return {boolean}
   */
  hasCallback(e) {
    for (const t of this._strategy.plugins)
      if (e in t)
        return !0;
    return !1;
  }
  /**
   * Runs all plugin callbacks matching the given name, in order, passing the
   * given param object (merged ith the current plugin state) as the only
   * argument.
   *
   * Note: since this method runs all plugins, it's not suitable for cases
   * where the return value of a callback needs to be applied prior to calling
   * the next callback. See
   * {@link workbox-strategies.StrategyHandler#iterateCallbacks}
   * below for how to handle that case.
   *
   * @param {string} name The name of the callback to run within each plugin.
   * @param {Object} param The object to pass as the first (and only) param
   *     when executing each callback. This object will be merged with the
   *     current plugin state prior to callback execution.
   */
  async runCallbacks(e, t) {
    for (const n of this.iterateCallbacks(e))
      await n(t);
  }
  /**
   * Accepts a callback and returns an iterable of matching plugin callbacks,
   * where each callback is wrapped with the current handler state (i.e. when
   * you call each callback, whatever object parameter you pass it will
   * be merged with the plugin's current state).
   *
   * @param {string} name The name fo the callback to run
   * @return {Array<Function>}
   */
  *iterateCallbacks(e) {
    for (const t of this._strategy.plugins)
      if (typeof t[e] == "function") {
        const n = this._pluginStateMap.get(t);
        yield (r) => {
          const i = Object.assign(Object.assign({}, r), { state: n });
          return t[e](i);
        };
      }
  }
  /**
   * Adds a promise to the
   * [extend lifetime promises]{@link https://w3c.github.io/ServiceWorker/#extendableevent-extend-lifetime-promises}
   * of the event associated with the request being handled (usually a
   * `FetchEvent`).
   *
   * Note: you can await
   * {@link workbox-strategies.StrategyHandler~doneWaiting}
   * to know when all added promises have settled.
   *
   * @param {Promise} promise A promise to add to the extend lifetime promises
   *     of the event that triggered the request.
   */
  waitUntil(e) {
    return this._extendLifetimePromises.push(e), e;
  }
  /**
   * Returns a promise that resolves once all promises passed to
   * {@link workbox-strategies.StrategyHandler~waitUntil}
   * have settled.
   *
   * Note: any work done after `doneWaiting()` settles should be manually
   * passed to an event's `waitUntil()` method (not this handler's
   * `waitUntil()` method), otherwise the service worker thread may be killed
   * prior to your work completing.
   */
  async doneWaiting() {
    for (; this._extendLifetimePromises.length; ) {
      const e = this._extendLifetimePromises.splice(0), n = (await Promise.allSettled(e)).find((a) => a.status === "rejected");
      if (n)
        throw n.reason;
    }
  }
  /**
   * Stops running the strategy and immediately resolves any pending
   * `waitUntil()` promises.
   */
  destroy() {
    this._handlerDeferred.resolve(null);
  }
  /**
   * This method will call cacheWillUpdate on the available plugins (or use
   * status === 200) to determine if the Response is safe and valid to cache.
   *
   * @param {Request} options.request
   * @param {Response} options.response
   * @return {Promise<Response|undefined>}
   *
   * @private
   */
  async _ensureResponseSafeToCache(e) {
    let t = e, n = !1;
    for (const a of this.iterateCallbacks("cacheWillUpdate"))
      if (t = await a({
        request: this.request,
        response: t,
        event: this.event
      }) || void 0, n = !0, !t)
        break;
    return n || t && t.status !== 200 && (t = void 0), t;
  }
}
class T {
  /**
   * Creates a new instance of the strategy and sets all documented option
   * properties as public instance properties.
   *
   * Note: if a custom strategy class extends the base Strategy class and does
   * not need more than these properties, it does not need to define its own
   * constructor.
   *
   * @param {Object} [options]
   * @param {string} [options.cacheName] Cache name to store and retrieve
   * requests. Defaults to the cache names provided by
   * {@link workbox-core.cacheNames}.
   * @param {Array<Object>} [options.plugins] [Plugins]{@link https://developers.google.com/web/tools/workbox/guides/using-plugins}
   * to use in conjunction with this caching strategy.
   * @param {Object} [options.fetchOptions] Values passed along to the
   * [`init`](https://developer.mozilla.org/en-US/docs/Web/API/WindowOrWorkerGlobalScope/fetch#Parameters)
   * of [non-navigation](https://github.com/GoogleChrome/workbox/issues/1796)
   * `fetch()` requests made by this strategy.
   * @param {Object} [options.matchOptions] The
   * [`CacheQueryOptions`]{@link https://w3c.github.io/ServiceWorker/#dictdef-cachequeryoptions}
   * for any `cache.match()` or `cache.put()` calls made by this strategy.
   */
  constructor(e = {}) {
    this.cacheName = D.getRuntimeName(e.cacheName), this.plugins = e.plugins || [], this.fetchOptions = e.fetchOptions, this.matchOptions = e.matchOptions;
  }
  /**
   * Perform a request strategy and returns a `Promise` that will resolve with
   * a `Response`, invoking all relevant plugin callbacks.
   *
   * When a strategy instance is registered with a Workbox
   * {@link workbox-routing.Route}, this method is automatically
   * called when the route matches.
   *
   * Alternatively, this method can be used in a standalone `FetchEvent`
   * listener by passing it to `event.respondWith()`.
   *
   * @param {FetchEvent|Object} options A `FetchEvent` or an object with the
   *     properties listed below.
   * @param {Request|string} options.request A request to run this strategy for.
   * @param {ExtendableEvent} options.event The event associated with the
   *     request.
   * @param {URL} [options.url]
   * @param {*} [options.params]
   */
  handle(e) {
    const [t] = this.handleAll(e);
    return t;
  }
  /**
   * Similar to {@link workbox-strategies.Strategy~handle}, but
   * instead of just returning a `Promise` that resolves to a `Response` it
   * it will return an tuple of `[response, done]` promises, where the former
   * (`response`) is equivalent to what `handle()` returns, and the latter is a
   * Promise that will resolve once any promises that were added to
   * `event.waitUntil()` as part of performing the strategy have completed.
   *
   * You can await the `done` promise to ensure any extra work performed by
   * the strategy (usually caching responses) completes successfully.
   *
   * @param {FetchEvent|Object} options A `FetchEvent` or an object with the
   *     properties listed below.
   * @param {Request|string} options.request A request to run this strategy for.
   * @param {ExtendableEvent} options.event The event associated with the
   *     request.
   * @param {URL} [options.url]
   * @param {*} [options.params]
   * @return {Array<Promise>} A tuple of [response, done]
   *     promises that can be used to determine when the response resolves as
   *     well as when the handler has completed all its work.
   */
  handleAll(e) {
    e instanceof FetchEvent && (e = {
      event: e,
      request: e.request
    });
    const t = e.event, n = typeof e.request == "string" ? new Request(e.request) : e.request, a = "params" in e ? e.params : void 0, r = new Ee(this, { event: t, request: n, params: a }), i = this._getResponse(r, n, t), o = this._awaitComplete(i, r, n, t);
    return [i, o];
  }
  async _getResponse(e, t, n) {
    await e.runCallbacks("handlerWillStart", { event: n, request: t });
    let a;
    try {
      if (a = await this._handle(t, e), !a || a.type === "error")
        throw new l("no-response", { url: t.url });
    } catch (r) {
      if (r instanceof Error) {
        for (const i of e.iterateCallbacks("handlerDidError"))
          if (a = await i({ error: r, event: n, request: t }), a)
            break;
      }
      if (!a)
        throw r;
    }
    for (const r of e.iterateCallbacks("handlerWillRespond"))
      a = await r({ event: n, request: t, response: a });
    return a;
  }
  async _awaitComplete(e, t, n, a) {
    let r, i;
    try {
      r = await e;
    } catch {
    }
    try {
      await t.runCallbacks("handlerDidRespond", {
        event: a,
        request: n,
        response: r
      }), await t.doneWaiting();
    } catch (o) {
      o instanceof Error && (i = o);
    }
    if (await t.runCallbacks("handlerDidComplete", {
      event: a,
      request: n,
      response: r,
      error: i
    }), t.destroy(), i)
      throw i;
  }
}
class m extends T {
  /**
   *
   * @param {Object} [options]
   * @param {string} [options.cacheName] Cache name to store and retrieve
   * requests. Defaults to the cache names provided by
   * {@link workbox-core.cacheNames}.
   * @param {Array<Object>} [options.plugins] {@link https://developers.google.com/web/tools/workbox/guides/using-plugins|Plugins}
   * to use in conjunction with this caching strategy.
   * @param {Object} [options.fetchOptions] Values passed along to the
   * {@link https://developer.mozilla.org/en-US/docs/Web/API/WindowOrWorkerGlobalScope/fetch#Parameters|init}
   * of all fetch() requests made by this strategy.
   * @param {Object} [options.matchOptions] The
   * {@link https://w3c.github.io/ServiceWorker/#dictdef-cachequeryoptions|CacheQueryOptions}
   * for any `cache.match()` or `cache.put()` calls made by this strategy.
   * @param {boolean} [options.fallbackToNetwork=true] Whether to attempt to
   * get the response from the network if there's a precache miss.
   */
  constructor(e = {}) {
    e.cacheName = D.getPrecacheName(e.cacheName), super(e), this._fallbackToNetwork = e.fallbackToNetwork !== !1, this.plugins.push(m.copyRedirectedCacheableResponsesPlugin);
  }
  /**
   * @private
   * @param {Request|string} request A request to run this strategy for.
   * @param {workbox-strategies.StrategyHandler} handler The event that
   *     triggered the request.
   * @return {Promise<Response>}
   */
  async _handle(e, t) {
    const n = await t.cacheMatch(e);
    return n || (t.event && t.event.type === "install" ? await this._handleInstall(e, t) : await this._handleFetch(e, t));
  }
  async _handleFetch(e, t) {
    let n;
    const a = t.params || {};
    if (this._fallbackToNetwork) {
      const r = a.integrity, i = e.integrity, o = !i || i === r;
      n = await t.fetch(new Request(e, {
        integrity: e.mode !== "no-cors" ? i || r : void 0
      })), r && o && e.mode !== "no-cors" && (this._useDefaultCacheabilityPluginIfNeeded(), await t.cachePut(e, n.clone()));
    } else
      throw new l("missing-precache-entry", {
        cacheName: this.cacheName,
        url: e.url
      });
    return n;
  }
  async _handleInstall(e, t) {
    this._useDefaultCacheabilityPluginIfNeeded();
    const n = await t.fetch(e);
    if (!await t.cachePut(e, n.clone()))
      throw new l("bad-precaching-response", {
        url: e.url,
        status: n.status
      });
    return n;
  }
  /**
   * This method is complex, as there a number of things to account for:
   *
   * The `plugins` array can be set at construction, and/or it might be added to
   * to at any time before the strategy is used.
   *
   * At the time the strategy is used (i.e. during an `install` event), there
   * needs to be at least one plugin that implements `cacheWillUpdate` in the
   * array, other than `copyRedirectedCacheableResponsesPlugin`.
   *
   * - If this method is called and there are no suitable `cacheWillUpdate`
   * plugins, we need to add `defaultPrecacheCacheabilityPlugin`.
   *
   * - If this method is called and there is exactly one `cacheWillUpdate`, then
   * we don't have to do anything (this might be a previously added
   * `defaultPrecacheCacheabilityPlugin`, or it might be a custom plugin).
   *
   * - If this method is called and there is more than one `cacheWillUpdate`,
   * then we need to check if one is `defaultPrecacheCacheabilityPlugin`. If so,
   * we need to remove it. (This situation is unlikely, but it could happen if
   * the strategy is used multiple times, the first without a `cacheWillUpdate`,
   * and then later on after manually adding a custom `cacheWillUpdate`.)
   *
   * See https://github.com/GoogleChrome/workbox/issues/2737 for more context.
   *
   * @private
   */
  _useDefaultCacheabilityPluginIfNeeded() {
    let e = null, t = 0;
    for (const [n, a] of this.plugins.entries())
      a !== m.copyRedirectedCacheableResponsesPlugin && (a === m.defaultPrecacheCacheabilityPlugin && (e = n), a.cacheWillUpdate && t++);
    t === 0 ? this.plugins.push(m.defaultPrecacheCacheabilityPlugin) : t > 1 && e !== null && this.plugins.splice(e, 1);
  }
}
m.defaultPrecacheCacheabilityPlugin = {
  async cacheWillUpdate({ response: s }) {
    return !s || s.status >= 400 ? null : s;
  }
};
m.copyRedirectedCacheableResponsesPlugin = {
  async cacheWillUpdate({ response: s }) {
    return s.redirected ? await ye(s) : s;
  }
};
class Ce {
  /**
   * Create a new PrecacheController.
   *
   * @param {Object} [options]
   * @param {string} [options.cacheName] The cache to use for precaching.
   * @param {string} [options.plugins] Plugins to use when precaching as well
   * as responding to fetch events for precached assets.
   * @param {boolean} [options.fallbackToNetwork=true] Whether to attempt to
   * get the response from the network if there's a precache miss.
   */
  constructor({ cacheName: e, plugins: t = [], fallbackToNetwork: n = !0 } = {}) {
    this._urlsToCacheKeys = /* @__PURE__ */ new Map(), this._urlsToCacheModes = /* @__PURE__ */ new Map(), this._cacheKeysToIntegrities = /* @__PURE__ */ new Map(), this._strategy = new m({
      cacheName: D.getPrecacheName(e),
      plugins: [
        ...t,
        new ge({ precacheController: this })
      ],
      fallbackToNetwork: n
    }), this.install = this.install.bind(this), this.activate = this.activate.bind(this);
  }
  /**
   * @type {workbox-precaching.PrecacheStrategy} The strategy created by this controller and
   * used to cache assets and respond to fetch events.
   */
  get strategy() {
    return this._strategy;
  }
  /**
   * Adds items to the precache list, removing any duplicates and
   * stores the files in the
   * {@link workbox-core.cacheNames|"precache cache"} when the service
   * worker installs.
   *
   * This method can be called multiple times.
   *
   * @param {Array<Object|string>} [entries=[]] Array of entries to precache.
   */
  precache(e) {
    this.addToCacheList(e), this._installAndActiveListenersAdded || (self.addEventListener("install", this.install), self.addEventListener("activate", this.activate), this._installAndActiveListenersAdded = !0);
  }
  /**
   * This method will add items to the precache list, removing duplicates
   * and ensuring the information is valid.
   *
   * @param {Array<workbox-precaching.PrecacheController.PrecacheEntry|string>} entries
   *     Array of entries to precache.
   */
  addToCacheList(e) {
    const t = [];
    for (const n of e) {
      typeof n == "string" ? t.push(n) : n && n.revision === void 0 && t.push(n.url);
      const { cacheKey: a, url: r } = fe(n), i = typeof n != "string" && n.revision ? "reload" : "default";
      if (this._urlsToCacheKeys.has(r) && this._urlsToCacheKeys.get(r) !== a)
        throw new l("add-to-cache-list-conflicting-entries", {
          firstEntry: this._urlsToCacheKeys.get(r),
          secondEntry: a
        });
      if (typeof n != "string" && n.integrity) {
        if (this._cacheKeysToIntegrities.has(a) && this._cacheKeysToIntegrities.get(a) !== n.integrity)
          throw new l("add-to-cache-list-conflicting-integrities", {
            url: r
          });
        this._cacheKeysToIntegrities.set(a, n.integrity);
      }
      if (this._urlsToCacheKeys.set(r, a), this._urlsToCacheModes.set(r, i), t.length > 0) {
        const o = `Workbox is precaching URLs without revision info: ${t.join(", ")}
This is generally NOT safe. Learn more at https://bit.ly/wb-precache`;
        console.warn(o);
      }
    }
  }
  /**
   * Precaches new and updated assets. Call this method from the service worker
   * install event.
   *
   * Note: this method calls `event.waitUntil()` for you, so you do not need
   * to call it yourself in your event handlers.
   *
   * @param {ExtendableEvent} event
   * @return {Promise<workbox-precaching.InstallResult>}
   */
  install(e) {
    return Q(e, async () => {
      const t = new pe();
      this.strategy.plugins.push(t);
      for (const [r, i] of this._urlsToCacheKeys) {
        const o = this._cacheKeysToIntegrities.get(i), c = this._urlsToCacheModes.get(r), h = new Request(r, {
          integrity: o,
          cache: c,
          credentials: "same-origin"
        });
        await Promise.all(this.strategy.handleAll({
          params: { cacheKey: i },
          request: h,
          event: e
        }));
      }
      const { updatedURLs: n, notUpdatedURLs: a } = t;
      return { updatedURLs: n, notUpdatedURLs: a };
    });
  }
  /**
   * Deletes assets that are no longer present in the current precache manifest.
   * Call this method from the service worker activate event.
   *
   * Note: this method calls `event.waitUntil()` for you, so you do not need
   * to call it yourself in your event handlers.
   *
   * @param {ExtendableEvent} event
   * @return {Promise<workbox-precaching.CleanupResult>}
   */
  activate(e) {
    return Q(e, async () => {
      const t = await self.caches.open(this.strategy.cacheName), n = await t.keys(), a = new Set(this._urlsToCacheKeys.values()), r = [];
      for (const i of n)
        a.has(i.url) || (await t.delete(i), r.push(i.url));
      return { deletedURLs: r };
    });
  }
  /**
   * Returns a mapping of a precached URL to the corresponding cache key, taking
   * into account the revision information for the URL.
   *
   * @return {Map<string, string>} A URL to cache key mapping.
   */
  getURLsToCacheKeys() {
    return this._urlsToCacheKeys;
  }
  /**
   * Returns a list of all the URLs that have been precached by the current
   * service worker.
   *
   * @return {Array<string>} The precached URLs.
   */
  getCachedURLs() {
    return [...this._urlsToCacheKeys.keys()];
  }
  /**
   * Returns the cache key used for storing a given URL. If that URL is
   * unversioned, like `/index.html', then the cache key will be the original
   * URL with a search parameter appended to it.
   *
   * @param {string} url A URL whose cache key you want to look up.
   * @return {string} The versioned URL that corresponds to a cache key
   * for the original URL, or undefined if that URL isn't precached.
   */
  getCacheKeyForURL(e) {
    const t = new URL(e, location.href);
    return this._urlsToCacheKeys.get(t.href);
  }
  /**
   * @param {string} url A cache key whose SRI you want to look up.
   * @return {string} The subresource integrity associated with the cache key,
   * or undefined if it's not set.
   */
  getIntegrityForCacheKey(e) {
    return this._cacheKeysToIntegrities.get(e);
  }
  /**
   * This acts as a drop-in replacement for
   * [`cache.match()`](https://developer.mozilla.org/en-US/docs/Web/API/Cache/match)
   * with the following differences:
   *
   * - It knows what the name of the precache is, and only checks in that cache.
   * - It allows you to pass in an "original" URL without versioning parameters,
   * and it will automatically look up the correct cache key for the currently
   * active revision of that URL.
   *
   * E.g., `matchPrecache('index.html')` will find the correct precached
   * response for the currently active service worker, even if the actual cache
   * key is `'/index.html?__WB_REVISION__=1234abcd'`.
   *
   * @param {string|Request} request The key (without revisioning parameters)
   * to look up in the precache.
   * @return {Promise<Response|undefined>}
   */
  async matchPrecache(e) {
    const t = e instanceof Request ? e.url : e, n = this.getCacheKeyForURL(t);
    if (n)
      return (await self.caches.open(this.strategy.cacheName)).match(n);
  }
  /**
   * Returns a function that looks up `url` in the precache (taking into
   * account revision information), and returns the corresponding `Response`.
   *
   * @param {string} url The precached URL which will be used to lookup the
   * `Response`.
   * @return {workbox-routing~handlerCallback}
   */
  createHandlerBoundToURL(e) {
    const t = this.getCacheKeyForURL(e);
    if (!t)
      throw new l("non-precached-url", { url: e });
    return (n) => (n.request = new Request(e), n.params = Object.assign({ cacheKey: t }, n.params), this.strategy.handle(n));
  }
}
let L;
const W = () => (L || (L = new Ce()), L);
try {
  self["workbox:routing:7.3.0"] && _();
} catch {
}
const se = "GET", N = (s) => s && typeof s == "object" ? s : { handle: s };
class y {
  /**
   * Constructor for Route class.
   *
   * @param {workbox-routing~matchCallback} match
   * A callback function that determines whether the route matches a given
   * `fetch` event by returning a non-falsy value.
   * @param {workbox-routing~handlerCallback} handler A callback
   * function that returns a Promise resolving to a Response.
   * @param {string} [method='GET'] The HTTP method to match the Route
   * against.
   */
  constructor(e, t, n = se) {
    this.handler = N(t), this.match = e, this.method = n;
  }
  /**
   *
   * @param {workbox-routing-handlerCallback} handler A callback
   * function that returns a Promise resolving to a Response
   */
  setCatchHandler(e) {
    this.catchHandler = N(e);
  }
}
class xe extends y {
  /**
   * If the regular expression contains
   * [capture groups]{@link https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/RegExp#grouping-back-references},
   * the captured values will be passed to the
   * {@link workbox-routing~handlerCallback} `params`
   * argument.
   *
   * @param {RegExp} regExp The regular expression to match against URLs.
   * @param {workbox-routing~handlerCallback} handler A callback
   * function that returns a Promise resulting in a Response.
   * @param {string} [method='GET'] The HTTP method to match the Route
   * against.
   */
  constructor(e, t, n) {
    const a = ({ url: r }) => {
      const i = e.exec(r.href);
      if (i && !(r.origin !== location.origin && i.index !== 0))
        return i.slice(1);
    };
    super(a, t, n);
  }
}
class De {
  /**
   * Initializes a new Router.
   */
  constructor() {
    this._routes = /* @__PURE__ */ new Map(), this._defaultHandlerMap = /* @__PURE__ */ new Map();
  }
  /**
   * @return {Map<string, Array<workbox-routing.Route>>} routes A `Map` of HTTP
   * method name ('GET', etc.) to an array of all the corresponding `Route`
   * instances that are registered.
   */
  get routes() {
    return this._routes;
  }
  /**
   * Adds a fetch event listener to respond to events when a route matches
   * the event's request.
   */
  addFetchListener() {
    self.addEventListener("fetch", (e) => {
      const { request: t } = e, n = this.handleRequest({ request: t, event: e });
      n && e.respondWith(n);
    });
  }
  /**
   * Adds a message event listener for URLs to cache from the window.
   * This is useful to cache resources loaded on the page prior to when the
   * service worker started controlling it.
   *
   * The format of the message data sent from the window should be as follows.
   * Where the `urlsToCache` array may consist of URL strings or an array of
   * URL string + `requestInit` object (the same as you'd pass to `fetch()`).
   *
   * ```
   * {
   *   type: 'CACHE_URLS',
   *   payload: {
   *     urlsToCache: [
   *       './script1.js',
   *       './script2.js',
   *       ['./script3.js', {mode: 'no-cors'}],
   *     ],
   *   },
   * }
   * ```
   */
  addCacheListener() {
    self.addEventListener("message", (e) => {
      if (e.data && e.data.type === "CACHE_URLS") {
        const { payload: t } = e.data, n = Promise.all(t.urlsToCache.map((a) => {
          typeof a == "string" && (a = [a]);
          const r = new Request(...a);
          return this.handleRequest({ request: r, event: e });
        }));
        e.waitUntil(n), e.ports && e.ports[0] && n.then(() => e.ports[0].postMessage(!0));
      }
    });
  }
  /**
   * Apply the routing rules to a FetchEvent object to get a Response from an
   * appropriate Route's handler.
   *
   * @param {Object} options
   * @param {Request} options.request The request to handle.
   * @param {ExtendableEvent} options.event The event that triggered the
   *     request.
   * @return {Promise<Response>|undefined} A promise is returned if a
   *     registered route can handle the request. If there is no matching
   *     route and there's no `defaultHandler`, `undefined` is returned.
   */
  handleRequest({ request: e, event: t }) {
    const n = new URL(e.url, location.href);
    if (!n.protocol.startsWith("http"))
      return;
    const a = n.origin === location.origin, { params: r, route: i } = this.findMatchingRoute({
      event: t,
      request: e,
      sameOrigin: a,
      url: n
    });
    let o = i && i.handler;
    const c = e.method;
    if (!o && this._defaultHandlerMap.has(c) && (o = this._defaultHandlerMap.get(c)), !o)
      return;
    let h;
    try {
      h = o.handle({ url: n, request: e, event: t, params: r });
    } catch (d) {
      h = Promise.reject(d);
    }
    const w = i && i.catchHandler;
    return h instanceof Promise && (this._catchHandler || w) && (h = h.catch(async (d) => {
      if (w)
        try {
          return await w.handle({ url: n, request: e, event: t, params: r });
        } catch (H) {
          H instanceof Error && (d = H);
        }
      if (this._catchHandler)
        return this._catchHandler.handle({ url: n, request: e, event: t });
      throw d;
    })), h;
  }
  /**
   * Checks a request and URL (and optionally an event) against the list of
   * registered routes, and if there's a match, returns the corresponding
   * route along with any params generated by the match.
   *
   * @param {Object} options
   * @param {URL} options.url
   * @param {boolean} options.sameOrigin The result of comparing `url.origin`
   *     against the current origin.
   * @param {Request} options.request The request to match.
   * @param {Event} options.event The corresponding event.
   * @return {Object} An object with `route` and `params` properties.
   *     They are populated if a matching route was found or `undefined`
   *     otherwise.
   */
  findMatchingRoute({ url: e, sameOrigin: t, request: n, event: a }) {
    const r = this._routes.get(n.method) || [];
    for (const i of r) {
      let o;
      const c = i.match({ url: e, sameOrigin: t, request: n, event: a });
      if (c)
        return o = c, (Array.isArray(o) && o.length === 0 || c.constructor === Object && // eslint-disable-line
        Object.keys(c).length === 0 || typeof c == "boolean") && (o = void 0), { route: i, params: o };
    }
    return {};
  }
  /**
   * Define a default `handler` that's called when no routes explicitly
   * match the incoming request.
   *
   * Each HTTP method ('GET', 'POST', etc.) gets its own default handler.
   *
   * Without a default handler, unmatched requests will go against the
   * network as if there were no service worker present.
   *
   * @param {workbox-routing~handlerCallback} handler A callback
   * function that returns a Promise resulting in a Response.
   * @param {string} [method='GET'] The HTTP method to associate with this
   * default handler. Each method has its own default.
   */
  setDefaultHandler(e, t = se) {
    this._defaultHandlerMap.set(t, N(e));
  }
  /**
   * If a Route throws an error while handling a request, this `handler`
   * will be called and given a chance to provide a response.
   *
   * @param {workbox-routing~handlerCallback} handler A callback
   * function that returns a Promise resulting in a Response.
   */
  setCatchHandler(e) {
    this._catchHandler = N(e);
  }
  /**
   * Registers a route with the router.
   *
   * @param {workbox-routing.Route} route The route to register.
   */
  registerRoute(e) {
    this._routes.has(e.method) || this._routes.set(e.method, []), this._routes.get(e.method).push(e);
  }
  /**
   * Unregisters a route with the router.
   *
   * @param {workbox-routing.Route} route The route to unregister.
   */
  unregisterRoute(e) {
    if (!this._routes.has(e.method))
      throw new l("unregister-route-but-not-found-with-method", {
        method: e.method
      });
    const t = this._routes.get(e.method).indexOf(e);
    if (t > -1)
      this._routes.get(e.method).splice(t, 1);
    else
      throw new l("unregister-route-route-not-registered");
  }
}
let R;
const Te = () => (R || (R = new De(), R.addFetchListener(), R.addCacheListener()), R);
function u(s, e, t) {
  let n;
  if (typeof s == "string") {
    const r = new URL(s, location.href), i = ({ url: o }) => o.href === r.href;
    n = new y(i, e, t);
  } else if (s instanceof RegExp)
    n = new xe(s, e, t);
  else if (typeof s == "function")
    n = new y(s, e, t);
  else if (s instanceof y)
    n = s;
  else
    throw new l("unsupported-route-type", {
      moduleName: "workbox-routing",
      funcName: "registerRoute",
      paramName: "capture"
    });
  return Te().registerRoute(n), n;
}
function ke(s, e = []) {
  for (const t of [...s.searchParams.keys()])
    e.some((n) => n.test(t)) && s.searchParams.delete(t);
  return s;
}
function* Ne(s, { ignoreURLParametersMatching: e = [/^utm_/, /^fbclid$/], directoryIndex: t = "index.html", cleanURLs: n = !0, urlManipulation: a } = {}) {
  const r = new URL(s, location.href);
  r.hash = "", yield r.href;
  const i = ke(r, e);
  if (yield i.href, t && i.pathname.endsWith("/")) {
    const o = new URL(i.href);
    o.pathname += t, yield o.href;
  }
  if (n) {
    const o = new URL(i.href);
    o.pathname += ".html", yield o.href;
  }
  if (a) {
    const o = a({ url: r });
    for (const c of o)
      yield c.href;
  }
}
class Se extends y {
  /**
   * @param {PrecacheController} precacheController A `PrecacheController`
   * instance used to both match requests and respond to fetch events.
   * @param {Object} [options] Options to control how requests are matched
   * against the list of precached URLs.
   * @param {string} [options.directoryIndex=index.html] The `directoryIndex` will
   * check cache entries for a URLs ending with '/' to see if there is a hit when
   * appending the `directoryIndex` value.
   * @param {Array<RegExp>} [options.ignoreURLParametersMatching=[/^utm_/, /^fbclid$/]] An
   * array of regex's to remove search params when looking for a cache match.
   * @param {boolean} [options.cleanURLs=true] The `cleanURLs` option will
   * check the cache for the URL with a `.html` added to the end of the end.
   * @param {workbox-precaching~urlManipulation} [options.urlManipulation]
   * This is a function that should take a URL and return an array of
   * alternative URLs that should be checked for precache matches.
   */
  constructor(e, t) {
    const n = ({ request: a }) => {
      const r = e.getURLsToCacheKeys();
      for (const i of Ne(a.url, t)) {
        const o = r.get(i);
        if (o) {
          const c = e.getIntegrityForCacheKey(o);
          return { cacheKey: o, integrity: c };
        }
      }
    };
    super(n, e.strategy);
  }
}
function Pe(s) {
  const e = W(), t = new Se(e, s);
  u(t);
}
const qe = "-precache-", Ue = async (s, e = qe) => {
  const n = (await self.caches.keys()).filter((a) => a.includes(e) && a.includes(self.registration.scope) && a !== s);
  return await Promise.all(n.map((a) => self.caches.delete(a))), n;
};
function Ie() {
  self.addEventListener("activate", (s) => {
    const e = D.getPrecacheName();
    s.waitUntil(Ue(e).then((t) => {
    }));
  });
}
function Le(s) {
  return W().createHandlerBoundToURL(s);
}
function Ae(s) {
  W().precache(s);
}
function ve(s, e) {
  Ae(s), Pe(e);
}
class Me extends y {
  /**
   * If both `denylist` and `allowlist` are provided, the `denylist` will
   * take precedence and the request will not match this route.
   *
   * The regular expressions in `allowlist` and `denylist`
   * are matched against the concatenated
   * [`pathname`]{@link https://developer.mozilla.org/en-US/docs/Web/API/HTMLHyperlinkElementUtils/pathname}
   * and [`search`]{@link https://developer.mozilla.org/en-US/docs/Web/API/HTMLHyperlinkElementUtils/search}
   * portions of the requested URL.
   *
   * *Note*: These RegExps may be evaluated against every destination URL during
   * a navigation. Avoid using
   * [complex RegExps](https://github.com/GoogleChrome/workbox/issues/3077),
   * or else your users may see delays when navigating your site.
   *
   * @param {workbox-routing~handlerCallback} handler A callback
   * function that returns a Promise resulting in a Response.
   * @param {Object} options
   * @param {Array<RegExp>} [options.denylist] If any of these patterns match,
   * the route will not handle the request (even if a allowlist RegExp matches).
   * @param {Array<RegExp>} [options.allowlist=[/./]] If any of these patterns
   * match the URL's pathname and search parameter, the route will handle the
   * request (assuming the denylist doesn't match).
   */
  constructor(e, { allowlist: t = [/./], denylist: n = [] } = {}) {
    super((a) => this._match(a), e), this._allowlist = t, this._denylist = n;
  }
  /**
   * Routes match handler.
   *
   * @param {Object} options
   * @param {URL} options.url
   * @param {Request} options.request
   * @return {boolean}
   *
   * @private
   */
  _match({ url: e, request: t }) {
    if (t && t.mode !== "navigate")
      return !1;
    const n = e.pathname + e.search;
    for (const a of this._denylist)
      if (a.test(n))
        return !1;
    return !!this._allowlist.some((a) => a.test(n));
  }
}
class j extends T {
  /**
   * @private
   * @param {Request|string} request A request to run this strategy for.
   * @param {workbox-strategies.StrategyHandler} handler The event that
   *     triggered the request.
   * @return {Promise<Response>}
   */
  async _handle(e, t) {
    let n = await t.cacheMatch(e), a;
    if (!n)
      try {
        n = await t.fetchAndCachePut(e);
      } catch (r) {
        r instanceof Error && (a = r);
      }
    if (!n)
      throw new l("no-response", { url: e.url, error: a });
    return n;
  }
}
const ne = {
  /**
   * Returns a valid response (to allow caching) if the status is 200 (OK) or
   * 0 (opaque).
   *
   * @param {Object} options
   * @param {Response} options.response
   * @return {Response|null}
   *
   * @private
   */
  cacheWillUpdate: async ({ response: s }) => s.status === 200 || s.status === 0 ? s : null
};
class Oe extends T {
  /**
   * @param {Object} [options]
   * @param {string} [options.cacheName] Cache name to store and retrieve
   * requests. Defaults to cache names provided by
   * {@link workbox-core.cacheNames}.
   * @param {Array<Object>} [options.plugins] [Plugins]{@link https://developers.google.com/web/tools/workbox/guides/using-plugins}
   * to use in conjunction with this caching strategy.
   * @param {Object} [options.fetchOptions] Values passed along to the
   * [`init`](https://developer.mozilla.org/en-US/docs/Web/API/WindowOrWorkerGlobalScope/fetch#Parameters)
   * of [non-navigation](https://github.com/GoogleChrome/workbox/issues/1796)
   * `fetch()` requests made by this strategy.
   * @param {Object} [options.matchOptions] [`CacheQueryOptions`](https://w3c.github.io/ServiceWorker/#dictdef-cachequeryoptions)
   * @param {number} [options.networkTimeoutSeconds] If set, any network requests
   * that fail to respond within the timeout will fallback to the cache.
   *
   * This option can be used to combat
   * "[lie-fi]{@link https://developers.google.com/web/fundamentals/performance/poor-connectivity/#lie-fi}"
   * scenarios.
   */
  constructor(e = {}) {
    super(e), this.plugins.some((t) => "cacheWillUpdate" in t) || this.plugins.unshift(ne), this._networkTimeoutSeconds = e.networkTimeoutSeconds || 0;
  }
  /**
   * @private
   * @param {Request|string} request A request to run this strategy for.
   * @param {workbox-strategies.StrategyHandler} handler The event that
   *     triggered the request.
   * @return {Promise<Response>}
   */
  async _handle(e, t) {
    const n = [], a = [];
    let r;
    if (this._networkTimeoutSeconds) {
      const { id: c, promise: h } = this._getTimeoutPromise({ request: e, logs: n, handler: t });
      r = c, a.push(h);
    }
    const i = this._getNetworkPromise({
      timeoutId: r,
      request: e,
      logs: n,
      handler: t
    });
    a.push(i);
    const o = await t.waitUntil((async () => await t.waitUntil(Promise.race(a)) || // If Promise.race() resolved with null, it might be due to a network
    // timeout + a cache miss. If that were to happen, we'd rather wait until
    // the networkPromise resolves instead of returning null.
    // Note that it's fine to await an already-resolved promise, so we don't
    // have to check to see if it's still "in flight".
    await i)());
    if (!o)
      throw new l("no-response", { url: e.url });
    return o;
  }
  /**
   * @param {Object} options
   * @param {Request} options.request
   * @param {Array} options.logs A reference to the logs array
   * @param {Event} options.event
   * @return {Promise<Response>}
   *
   * @private
   */
  _getTimeoutPromise({ request: e, logs: t, handler: n }) {
    let a;
    return {
      promise: new Promise((i) => {
        a = setTimeout(async () => {
          i(await n.cacheMatch(e));
        }, this._networkTimeoutSeconds * 1e3);
      }),
      id: a
    };
  }
  /**
   * @param {Object} options
   * @param {number|undefined} options.timeoutId
   * @param {Request} options.request
   * @param {Array} options.logs A reference to the logs Array.
   * @param {Event} options.event
   * @return {Promise<Response>}
   *
   * @private
   */
  async _getNetworkPromise({ timeoutId: e, request: t, logs: n, handler: a }) {
    let r, i;
    try {
      i = await a.fetchAndCachePut(t);
    } catch (o) {
      o instanceof Error && (r = o);
    }
    return e && clearTimeout(e), (r || !i) && (i = await a.cacheMatch(t)), i;
  }
}
class S extends T {
  /**
   * @param {Object} [options]
   * @param {Array<Object>} [options.plugins] [Plugins]{@link https://developers.google.com/web/tools/workbox/guides/using-plugins}
   * to use in conjunction with this caching strategy.
   * @param {Object} [options.fetchOptions] Values passed along to the
   * [`init`](https://developer.mozilla.org/en-US/docs/Web/API/WindowOrWorkerGlobalScope/fetch#Parameters)
   * of [non-navigation](https://github.com/GoogleChrome/workbox/issues/1796)
   * `fetch()` requests made by this strategy.
   * @param {number} [options.networkTimeoutSeconds] If set, any network requests
   * that fail to respond within the timeout will result in a network error.
   */
  constructor(e = {}) {
    super(e), this._networkTimeoutSeconds = e.networkTimeoutSeconds || 0;
  }
  /**
   * @private
   * @param {Request|string} request A request to run this strategy for.
   * @param {workbox-strategies.StrategyHandler} handler The event that
   *     triggered the request.
   * @return {Promise<Response>}
   */
  async _handle(e, t) {
    let n, a;
    try {
      const r = [
        t.fetch(e)
      ];
      if (this._networkTimeoutSeconds) {
        const i = te(this._networkTimeoutSeconds * 1e3);
        r.push(i);
      }
      if (a = await Promise.race(r), !a)
        throw new Error(`Timed out the network response after ${this._networkTimeoutSeconds} seconds.`);
    } catch (r) {
      r instanceof Error && (n = r);
    }
    if (!a)
      throw new l("no-response", { url: e.url, error: n });
    return a;
  }
}
class ae extends T {
  /**
   * @param {Object} [options]
   * @param {string} [options.cacheName] Cache name to store and retrieve
   * requests. Defaults to cache names provided by
   * {@link workbox-core.cacheNames}.
   * @param {Array<Object>} [options.plugins] [Plugins]{@link https://developers.google.com/web/tools/workbox/guides/using-plugins}
   * to use in conjunction with this caching strategy.
   * @param {Object} [options.fetchOptions] Values passed along to the
   * [`init`](https://developer.mozilla.org/en-US/docs/Web/API/WindowOrWorkerGlobalScope/fetch#Parameters)
   * of [non-navigation](https://github.com/GoogleChrome/workbox/issues/1796)
   * `fetch()` requests made by this strategy.
   * @param {Object} [options.matchOptions] [`CacheQueryOptions`](https://w3c.github.io/ServiceWorker/#dictdef-cachequeryoptions)
   */
  constructor(e = {}) {
    super(e), this.plugins.some((t) => "cacheWillUpdate" in t) || this.plugins.unshift(ne);
  }
  /**
   * @private
   * @param {Request|string} request A request to run this strategy for.
   * @param {workbox-strategies.StrategyHandler} handler The event that
   *     triggered the request.
   * @return {Promise<Response>}
   */
  async _handle(e, t) {
    const n = t.fetchAndCachePut(e).catch(() => {
    });
    t.waitUntil(n);
    let a = await t.cacheMatch(e), r;
    if (!a) try {
      a = await n;
    } catch (i) {
      i instanceof Error && (r = i);
    }
    if (!a)
      throw new l("no-response", { url: e.url, error: r });
    return a;
  }
}
function re(s) {
  s.then(() => {
  });
}
const Be = (s, e) => e.some((t) => s instanceof t);
let $, G;
function Ke() {
  return $ || ($ = [
    IDBDatabase,
    IDBObjectStore,
    IDBIndex,
    IDBCursor,
    IDBTransaction
  ]);
}
function We() {
  return G || (G = [
    IDBCursor.prototype.advance,
    IDBCursor.prototype.continue,
    IDBCursor.prototype.continuePrimaryKey
  ]);
}
const ie = /* @__PURE__ */ new WeakMap(), B = /* @__PURE__ */ new WeakMap(), oe = /* @__PURE__ */ new WeakMap(), A = /* @__PURE__ */ new WeakMap(), F = /* @__PURE__ */ new WeakMap();
function je(s) {
  const e = new Promise((t, n) => {
    const a = () => {
      s.removeEventListener("success", r), s.removeEventListener("error", i);
    }, r = () => {
      t(g(s.result)), a();
    }, i = () => {
      n(s.error), a();
    };
    s.addEventListener("success", r), s.addEventListener("error", i);
  });
  return e.then((t) => {
    t instanceof IDBCursor && ie.set(t, s);
  }).catch(() => {
  }), F.set(e, s), e;
}
function Fe(s) {
  if (B.has(s))
    return;
  const e = new Promise((t, n) => {
    const a = () => {
      s.removeEventListener("complete", r), s.removeEventListener("error", i), s.removeEventListener("abort", i);
    }, r = () => {
      t(), a();
    }, i = () => {
      n(s.error || new DOMException("AbortError", "AbortError")), a();
    };
    s.addEventListener("complete", r), s.addEventListener("error", i), s.addEventListener("abort", i);
  });
  B.set(s, e);
}
let K = {
  get(s, e, t) {
    if (s instanceof IDBTransaction) {
      if (e === "done")
        return B.get(s);
      if (e === "objectStoreNames")
        return s.objectStoreNames || oe.get(s);
      if (e === "store")
        return t.objectStoreNames[1] ? void 0 : t.objectStore(t.objectStoreNames[0]);
    }
    return g(s[e]);
  },
  set(s, e, t) {
    return s[e] = t, !0;
  },
  has(s, e) {
    return s instanceof IDBTransaction && (e === "done" || e === "store") ? !0 : e in s;
  }
};
function He(s) {
  K = s(K);
}
function Qe(s) {
  return s === IDBDatabase.prototype.transaction && !("objectStoreNames" in IDBTransaction.prototype) ? function(e, ...t) {
    const n = s.call(v(this), e, ...t);
    return oe.set(n, e.sort ? e.sort() : [e]), g(n);
  } : We().includes(s) ? function(...e) {
    return s.apply(v(this), e), g(ie.get(this));
  } : function(...e) {
    return g(s.apply(v(this), e));
  };
}
function Ve(s) {
  return typeof s == "function" ? Qe(s) : (s instanceof IDBTransaction && Fe(s), Be(s, Ke()) ? new Proxy(s, K) : s);
}
function g(s) {
  if (s instanceof IDBRequest)
    return je(s);
  if (A.has(s))
    return A.get(s);
  const e = Ve(s);
  return e !== s && (A.set(s, e), F.set(e, s)), e;
}
const v = (s) => F.get(s);
function ce(s, e, { blocked: t, upgrade: n, blocking: a, terminated: r } = {}) {
  const i = indexedDB.open(s, e), o = g(i);
  return n && i.addEventListener("upgradeneeded", (c) => {
    n(g(i.result), c.oldVersion, c.newVersion, g(i.transaction), c);
  }), t && i.addEventListener("blocked", (c) => t(
    // Casting due to https://github.com/microsoft/TypeScript-DOM-lib-generator/pull/1405
    c.oldVersion,
    c.newVersion,
    c
  )), o.then((c) => {
    r && c.addEventListener("close", () => r()), a && c.addEventListener("versionchange", (h) => a(h.oldVersion, h.newVersion, h));
  }).catch(() => {
  }), o;
}
function $e(s, { blocked: e } = {}) {
  const t = indexedDB.deleteDatabase(s);
  return e && t.addEventListener("blocked", (n) => e(
    // Casting due to https://github.com/microsoft/TypeScript-DOM-lib-generator/pull/1405
    n.oldVersion,
    n
  )), g(t).then(() => {
  });
}
const Ge = ["get", "getKey", "getAll", "getAllKeys", "count"], ze = ["put", "add", "delete", "clear"], M = /* @__PURE__ */ new Map();
function z(s, e) {
  if (!(s instanceof IDBDatabase && !(e in s) && typeof e == "string"))
    return;
  if (M.get(e))
    return M.get(e);
  const t = e.replace(/FromIndex$/, ""), n = e !== t, a = ze.includes(t);
  if (
    // Bail if the target doesn't exist on the target. Eg, getAll isn't in Edge.
    !(t in (n ? IDBIndex : IDBObjectStore).prototype) || !(a || Ge.includes(t))
  )
    return;
  const r = async function(i, ...o) {
    const c = this.transaction(i, a ? "readwrite" : "readonly");
    let h = c.store;
    return n && (h = h.index(o.shift())), (await Promise.all([
      h[t](...o),
      a && c.done
    ]))[0];
  };
  return M.set(e, r), r;
}
He((s) => ({
  ...s,
  get: (e, t, n) => z(e, t) || s.get(e, t, n),
  has: (e, t) => !!z(e, t) || s.has(e, t)
}));
try {
  self["workbox:expiration:7.3.0"] && _();
} catch {
}
const Ye = "workbox-expiration", E = "cache-entries", Y = (s) => {
  const e = new URL(s, location.href);
  return e.hash = "", e.href;
};
class Je {
  /**
   *
   * @param {string} cacheName
   *
   * @private
   */
  constructor(e) {
    this._db = null, this._cacheName = e;
  }
  /**
   * Performs an upgrade of indexedDB.
   *
   * @param {IDBPDatabase<CacheDbSchema>} db
   *
   * @private
   */
  _upgradeDb(e) {
    const t = e.createObjectStore(E, { keyPath: "id" });
    t.createIndex("cacheName", "cacheName", { unique: !1 }), t.createIndex("timestamp", "timestamp", { unique: !1 });
  }
  /**
   * Performs an upgrade of indexedDB and deletes deprecated DBs.
   *
   * @param {IDBPDatabase<CacheDbSchema>} db
   *
   * @private
   */
  _upgradeDbAndDeleteOldDbs(e) {
    this._upgradeDb(e), this._cacheName && $e(this._cacheName);
  }
  /**
   * @param {string} url
   * @param {number} timestamp
   *
   * @private
   */
  async setTimestamp(e, t) {
    e = Y(e);
    const n = {
      url: e,
      timestamp: t,
      cacheName: this._cacheName,
      // Creating an ID from the URL and cache name won't be necessary once
      // Edge switches to Chromium and all browsers we support work with
      // array keyPaths.
      id: this._getId(e)
    }, r = (await this.getDb()).transaction(E, "readwrite", {
      durability: "relaxed"
    });
    await r.store.put(n), await r.done;
  }
  /**
   * Returns the timestamp stored for a given URL.
   *
   * @param {string} url
   * @return {number | undefined}
   *
   * @private
   */
  async getTimestamp(e) {
    const n = await (await this.getDb()).get(E, this._getId(e));
    return n == null ? void 0 : n.timestamp;
  }
  /**
   * Iterates through all the entries in the object store (from newest to
   * oldest) and removes entries once either `maxCount` is reached or the
   * entry's timestamp is less than `minTimestamp`.
   *
   * @param {number} minTimestamp
   * @param {number} maxCount
   * @return {Array<string>}
   *
   * @private
   */
  async expireEntries(e, t) {
    const n = await this.getDb();
    let a = await n.transaction(E).store.index("timestamp").openCursor(null, "prev");
    const r = [];
    let i = 0;
    for (; a; ) {
      const c = a.value;
      c.cacheName === this._cacheName && (e && c.timestamp < e || t && i >= t ? r.push(a.value) : i++), a = await a.continue();
    }
    const o = [];
    for (const c of r)
      await n.delete(E, c.id), o.push(c.url);
    return o;
  }
  /**
   * Takes a URL and returns an ID that will be unique in the object store.
   *
   * @param {string} url
   * @return {string}
   *
   * @private
   */
  _getId(e) {
    return this._cacheName + "|" + Y(e);
  }
  /**
   * Returns an open connection to the database.
   *
   * @private
   */
  async getDb() {
    return this._db || (this._db = await ce(Ye, 1, {
      upgrade: this._upgradeDbAndDeleteOldDbs.bind(this)
    })), this._db;
  }
}
class Xe {
  /**
   * To construct a new CacheExpiration instance you must provide at least
   * one of the `config` properties.
   *
   * @param {string} cacheName Name of the cache to apply restrictions to.
   * @param {Object} config
   * @param {number} [config.maxEntries] The maximum number of entries to cache.
   * Entries used the least will be removed as the maximum is reached.
   * @param {number} [config.maxAgeSeconds] The maximum age of an entry before
   * it's treated as stale and removed.
   * @param {Object} [config.matchOptions] The [`CacheQueryOptions`](https://developer.mozilla.org/en-US/docs/Web/API/Cache/delete#Parameters)
   * that will be used when calling `delete()` on the cache.
   */
  constructor(e, t = {}) {
    this._isRunning = !1, this._rerunRequested = !1, this._maxEntries = t.maxEntries, this._maxAgeSeconds = t.maxAgeSeconds, this._matchOptions = t.matchOptions, this._cacheName = e, this._timestampModel = new Je(e);
  }
  /**
   * Expires entries for the given cache and given criteria.
   */
  async expireEntries() {
    if (this._isRunning) {
      this._rerunRequested = !0;
      return;
    }
    this._isRunning = !0;
    const e = this._maxAgeSeconds ? Date.now() - this._maxAgeSeconds * 1e3 : 0, t = await this._timestampModel.expireEntries(e, this._maxEntries), n = await self.caches.open(this._cacheName);
    for (const a of t)
      await n.delete(a, this._matchOptions);
    this._isRunning = !1, this._rerunRequested && (this._rerunRequested = !1, re(this.expireEntries()));
  }
  /**
   * Update the timestamp for the given URL. This ensures the when
   * removing entries based on maximum entries, most recently used
   * is accurate or when expiring, the timestamp is up-to-date.
   *
   * @param {string} url
   */
  async updateTimestamp(e) {
    await this._timestampModel.setTimestamp(e, Date.now());
  }
  /**
   * Can be used to check if a URL has expired or not before it's used.
   *
   * This requires a look up from IndexedDB, so can be slow.
   *
   * Note: This method will not remove the cached entry, call
   * `expireEntries()` to remove indexedDB and Cache entries.
   *
   * @param {string} url
   * @return {boolean}
   */
  async isURLExpired(e) {
    if (this._maxAgeSeconds) {
      const t = await this._timestampModel.getTimestamp(e), n = Date.now() - this._maxAgeSeconds * 1e3;
      return t !== void 0 ? t < n : !0;
    } else
      return !1;
  }
  /**
   * Removes the IndexedDB object store used to keep track of cache expiration
   * metadata.
   */
  async delete() {
    this._rerunRequested = !1, await this._timestampModel.expireEntries(1 / 0);
  }
}
function Ze(s) {
  ee.add(s);
}
class P {
  /**
   * @param {ExpirationPluginOptions} config
   * @param {number} [config.maxEntries] The maximum number of entries to cache.
   * Entries used the least will be removed as the maximum is reached.
   * @param {number} [config.maxAgeSeconds] The maximum age of an entry before
   * it's treated as stale and removed.
   * @param {Object} [config.matchOptions] The [`CacheQueryOptions`](https://developer.mozilla.org/en-US/docs/Web/API/Cache/delete#Parameters)
   * that will be used when calling `delete()` on the cache.
   * @param {boolean} [config.purgeOnQuotaError] Whether to opt this cache in to
   * automatic deletion if the available storage quota has been exceeded.
   */
  constructor(e = {}) {
    this.cachedResponseWillBeUsed = async ({ event: t, request: n, cacheName: a, cachedResponse: r }) => {
      if (!r)
        return null;
      const i = this._isResponseDateFresh(r), o = this._getCacheExpiration(a);
      re(o.expireEntries());
      const c = o.updateTimestamp(n.url);
      if (t)
        try {
          t.waitUntil(c);
        } catch {
        }
      return i ? r : null;
    }, this.cacheDidUpdate = async ({ cacheName: t, request: n }) => {
      const a = this._getCacheExpiration(t);
      await a.updateTimestamp(n.url), await a.expireEntries();
    }, this._config = e, this._maxAgeSeconds = e.maxAgeSeconds, this._cacheExpirations = /* @__PURE__ */ new Map(), e.purgeOnQuotaError && Ze(() => this.deleteCacheAndMetadata());
  }
  /**
   * A simple helper method to return a CacheExpiration instance for a given
   * cache name.
   *
   * @param {string} cacheName
   * @return {CacheExpiration}
   *
   * @private
   */
  _getCacheExpiration(e) {
    if (e === D.getRuntimeName())
      throw new l("expire-custom-caches-only");
    let t = this._cacheExpirations.get(e);
    return t || (t = new Xe(e, this._config), this._cacheExpirations.set(e, t)), t;
  }
  /**
   * @param {Response} cachedResponse
   * @return {boolean}
   *
   * @private
   */
  _isResponseDateFresh(e) {
    if (!this._maxAgeSeconds)
      return !0;
    const t = this._getDateHeaderTimestamp(e);
    if (t === null)
      return !0;
    const n = Date.now();
    return t >= n - this._maxAgeSeconds * 1e3;
  }
  /**
   * This method will extract the data header and parse it into a useful
   * value.
   *
   * @param {Response} cachedResponse
   * @return {number|null}
   *
   * @private
   */
  _getDateHeaderTimestamp(e) {
    if (!e.headers.has("date"))
      return null;
    const t = e.headers.get("date"), a = new Date(t).getTime();
    return isNaN(a) ? null : a;
  }
  /**
   * This is a helper method that performs two operations:
   *
   * - Deletes *all* the underlying Cache instances associated with this plugin
   * instance, by calling caches.delete() on your behalf.
   * - Deletes the metadata from IndexedDB used to keep track of expiration
   * details for each Cache instance.
   *
   * When using cache expiration, calling this method is preferable to calling
   * `caches.delete()` directly, since this will ensure that the IndexedDB
   * metadata is also cleanly removed and open IndexedDB instances are deleted.
   *
   * Note that if you're *not* using cache expiration for a given cache, calling
   * `caches.delete()` and passing in the cache's name should be sufficient.
   * There is no Workbox-specific method needed for cleanup in that case.
   */
  async deleteCacheAndMetadata() {
    for (const [e, t] of this._cacheExpirations)
      await self.caches.delete(e), await t.delete();
    this._cacheExpirations = /* @__PURE__ */ new Map();
  }
}
try {
  self["workbox:cacheable-response:7.3.0"] && _();
} catch {
}
class et {
  /**
   * To construct a new CacheableResponse instance you must provide at least
   * one of the `config` properties.
   *
   * If both `statuses` and `headers` are specified, then both conditions must
   * be met for the `Response` to be considered cacheable.
   *
   * @param {Object} config
   * @param {Array<number>} [config.statuses] One or more status codes that a
   * `Response` can have and be considered cacheable.
   * @param {Object<string,string>} [config.headers] A mapping of header names
   * and expected values that a `Response` can have and be considered cacheable.
   * If multiple headers are provided, only one needs to be present.
   */
  constructor(e = {}) {
    this._statuses = e.statuses, this._headers = e.headers;
  }
  /**
   * Checks a response to see whether it's cacheable or not, based on this
   * object's configuration.
   *
   * @param {Response} response The response whose cacheability is being
   * checked.
   * @return {boolean} `true` if the `Response` is cacheable, and `false`
   * otherwise.
   */
  isResponseCacheable(e) {
    let t = !0;
    return this._statuses && (t = this._statuses.includes(e.status)), this._headers && t && (t = Object.keys(this._headers).some((n) => e.headers.get(n) === this._headers[n])), t;
  }
}
class q {
  /**
   * To construct a new CacheableResponsePlugin instance you must provide at
   * least one of the `config` properties.
   *
   * If both `statuses` and `headers` are specified, then both conditions must
   * be met for the `Response` to be considered cacheable.
   *
   * @param {Object} config
   * @param {Array<number>} [config.statuses] One or more status codes that a
   * `Response` can have and be considered cacheable.
   * @param {Object<string,string>} [config.headers] A mapping of header names
   * and expected values that a `Response` can have and be considered cacheable.
   * If multiple headers are provided, only one needs to be present.
   */
  constructor(e) {
    this.cacheWillUpdate = async ({ response: t }) => this._cacheableResponse.isResponseCacheable(t) ? t : null, this._cacheableResponse = new et(e);
  }
}
try {
  self["workbox:background-sync:7.3.0"] && _();
} catch {
}
const J = 3, tt = "workbox-background-sync", f = "requests", C = "queueName";
class st {
  constructor() {
    this._db = null;
  }
  /**
   * Add QueueStoreEntry to underlying db.
   *
   * @param {UnidentifiedQueueStoreEntry} entry
   */
  async addEntry(e) {
    const n = (await this.getDb()).transaction(f, "readwrite", {
      durability: "relaxed"
    });
    await n.store.add(e), await n.done;
  }
  /**
   * Returns the first entry id in the ObjectStore.
   *
   * @return {number | undefined}
   */
  async getFirstEntryId() {
    const t = await (await this.getDb()).transaction(f).store.openCursor();
    return t == null ? void 0 : t.value.id;
  }
  /**
   * Get all the entries filtered by index
   *
   * @param queueName
   * @return {Promise<QueueStoreEntry[]>}
   */
  async getAllEntriesByQueueName(e) {
    const n = await (await this.getDb()).getAllFromIndex(f, C, IDBKeyRange.only(e));
    return n || new Array();
  }
  /**
   * Returns the number of entries filtered by index
   *
   * @param queueName
   * @return {Promise<number>}
   */
  async getEntryCountByQueueName(e) {
    return (await this.getDb()).countFromIndex(f, C, IDBKeyRange.only(e));
  }
  /**
   * Deletes a single entry by id.
   *
   * @param {number} id the id of the entry to be deleted
   */
  async deleteEntry(e) {
    await (await this.getDb()).delete(f, e);
  }
  /**
   *
   * @param queueName
   * @returns {Promise<QueueStoreEntry | undefined>}
   */
  async getFirstEntryByQueueName(e) {
    return await this.getEndEntryFromIndex(IDBKeyRange.only(e), "next");
  }
  /**
   *
   * @param queueName
   * @returns {Promise<QueueStoreEntry | undefined>}
   */
  async getLastEntryByQueueName(e) {
    return await this.getEndEntryFromIndex(IDBKeyRange.only(e), "prev");
  }
  /**
   * Returns either the first or the last entries, depending on direction.
   * Filtered by index.
   *
   * @param {IDBCursorDirection} direction
   * @param {IDBKeyRange} query
   * @return {Promise<QueueStoreEntry | undefined>}
   * @private
   */
  async getEndEntryFromIndex(e, t) {
    const a = await (await this.getDb()).transaction(f).store.index(C).openCursor(e, t);
    return a == null ? void 0 : a.value;
  }
  /**
   * Returns an open connection to the database.
   *
   * @private
   */
  async getDb() {
    return this._db || (this._db = await ce(tt, J, {
      upgrade: this._upgradeDb
    })), this._db;
  }
  /**
   * Upgrades QueueDB
   *
   * @param {IDBPDatabase<QueueDBSchema>} db
   * @param {number} oldVersion
   * @private
   */
  _upgradeDb(e, t) {
    t > 0 && t < J && e.objectStoreNames.contains(f) && e.deleteObjectStore(f), e.createObjectStore(f, {
      autoIncrement: !0,
      keyPath: "id"
    }).createIndex(C, C, { unique: !1 });
  }
}
class nt {
  /**
   * Associates this instance with a Queue instance, so entries added can be
   * identified by their queue name.
   *
   * @param {string} queueName
   */
  constructor(e) {
    this._queueName = e, this._queueDb = new st();
  }
  /**
   * Append an entry last in the queue.
   *
   * @param {Object} entry
   * @param {Object} entry.requestData
   * @param {number} [entry.timestamp]
   * @param {Object} [entry.metadata]
   */
  async pushEntry(e) {
    delete e.id, e.queueName = this._queueName, await this._queueDb.addEntry(e);
  }
  /**
   * Prepend an entry first in the queue.
   *
   * @param {Object} entry
   * @param {Object} entry.requestData
   * @param {number} [entry.timestamp]
   * @param {Object} [entry.metadata]
   */
  async unshiftEntry(e) {
    const t = await this._queueDb.getFirstEntryId();
    t ? e.id = t - 1 : delete e.id, e.queueName = this._queueName, await this._queueDb.addEntry(e);
  }
  /**
   * Removes and returns the last entry in the queue matching the `queueName`.
   *
   * @return {Promise<QueueStoreEntry|undefined>}
   */
  async popEntry() {
    return this._removeEntry(await this._queueDb.getLastEntryByQueueName(this._queueName));
  }
  /**
   * Removes and returns the first entry in the queue matching the `queueName`.
   *
   * @return {Promise<QueueStoreEntry|undefined>}
   */
  async shiftEntry() {
    return this._removeEntry(await this._queueDb.getFirstEntryByQueueName(this._queueName));
  }
  /**
   * Returns all entries in the store matching the `queueName`.
   *
   * @param {Object} options See {@link workbox-background-sync.Queue~getAll}
   * @return {Promise<Array<Object>>}
   */
  async getAll() {
    return await this._queueDb.getAllEntriesByQueueName(this._queueName);
  }
  /**
   * Returns the number of entries in the store matching the `queueName`.
   *
   * @param {Object} options See {@link workbox-background-sync.Queue~size}
   * @return {Promise<number>}
   */
  async size() {
    return await this._queueDb.getEntryCountByQueueName(this._queueName);
  }
  /**
   * Deletes the entry for the given ID.
   *
   * WARNING: this method does not ensure the deleted entry belongs to this
   * queue (i.e. matches the `queueName`). But this limitation is acceptable
   * as this class is not publicly exposed. An additional check would make
   * this method slower than it needs to be.
   *
   * @param {number} id
   */
  async deleteEntry(e) {
    await this._queueDb.deleteEntry(e);
  }
  /**
   * Removes and returns the first or last entry in the queue (based on the
   * `direction` argument) matching the `queueName`.
   *
   * @return {Promise<QueueStoreEntry|undefined>}
   * @private
   */
  async _removeEntry(e) {
    return e && await this.deleteEntry(e.id), e;
  }
}
const at = [
  "method",
  "referrer",
  "referrerPolicy",
  "mode",
  "credentials",
  "cache",
  "redirect",
  "integrity",
  "keepalive"
];
class x {
  /**
   * Converts a Request object to a plain object that can be structured
   * cloned or JSON-stringified.
   *
   * @param {Request} request
   * @return {Promise<StorableRequest>}
   */
  static async fromRequest(e) {
    const t = {
      url: e.url,
      headers: {}
    };
    e.method !== "GET" && (t.body = await e.clone().arrayBuffer());
    for (const [n, a] of e.headers.entries())
      t.headers[n] = a;
    for (const n of at)
      e[n] !== void 0 && (t[n] = e[n]);
    return new x(t);
  }
  /**
   * Accepts an object of request data that can be used to construct a
   * `Request` but can also be stored in IndexedDB.
   *
   * @param {Object} requestData An object of request data that includes the
   *     `url` plus any relevant properties of
   *     [requestInit]{@link https://fetch.spec.whatwg.org/#requestinit}.
   */
  constructor(e) {
    e.mode === "navigate" && (e.mode = "same-origin"), this._requestData = e;
  }
  /**
   * Returns a deep clone of the instances `_requestData` object.
   *
   * @return {Object}
   */
  toObject() {
    const e = Object.assign({}, this._requestData);
    return e.headers = Object.assign({}, this._requestData.headers), e.body && (e.body = e.body.slice(0)), e;
  }
  /**
   * Converts this instance to a Request.
   *
   * @return {Request}
   */
  toRequest() {
    return new Request(this._requestData.url, this._requestData);
  }
  /**
   * Creates and returns a deep clone of the instance.
   *
   * @return {StorableRequest}
   */
  clone() {
    return new x(this.toObject());
  }
}
const X = "workbox-background-sync", rt = 60 * 24 * 7, O = /* @__PURE__ */ new Set(), Z = (s) => {
  const e = {
    request: new x(s.requestData).toRequest(),
    timestamp: s.timestamp
  };
  return s.metadata && (e.metadata = s.metadata), e;
};
class it {
  /**
   * Creates an instance of Queue with the given options
   *
   * @param {string} name The unique name for this queue. This name must be
   *     unique as it's used to register sync events and store requests
   *     in IndexedDB specific to this instance. An error will be thrown if
   *     a duplicate name is detected.
   * @param {Object} [options]
   * @param {Function} [options.onSync] A function that gets invoked whenever
   *     the 'sync' event fires. The function is invoked with an object
   *     containing the `queue` property (referencing this instance), and you
   *     can use the callback to customize the replay behavior of the queue.
   *     When not set the `replayRequests()` method is called.
   *     Note: if the replay fails after a sync event, make sure you throw an
   *     error, so the browser knows to retry the sync event later.
   * @param {number} [options.maxRetentionTime=7 days] The amount of time (in
   *     minutes) a request may be retried. After this amount of time has
   *     passed, the request will be deleted from the queue.
   * @param {boolean} [options.forceSyncFallback=false] If `true`, instead
   *     of attempting to use background sync events, always attempt to replay
   *     queued request at service worker startup. Most folks will not need
   *     this, unless you explicitly target a runtime like Electron that
   *     exposes the interfaces for background sync, but does not have a working
   *     implementation.
   */
  constructor(e, { forceSyncFallback: t, onSync: n, maxRetentionTime: a } = {}) {
    if (this._syncInProgress = !1, this._requestsAddedDuringSync = !1, O.has(e))
      throw new l("duplicate-queue-name", { name: e });
    O.add(e), this._name = e, this._onSync = n || this.replayRequests, this._maxRetentionTime = a || rt, this._forceSyncFallback = !!t, this._queueStore = new nt(this._name), this._addSyncListener();
  }
  /**
   * @return {string}
   */
  get name() {
    return this._name;
  }
  /**
   * Stores the passed request in IndexedDB (with its timestamp and any
   * metadata) at the end of the queue.
   *
   * @param {QueueEntry} entry
   * @param {Request} entry.request The request to store in the queue.
   * @param {Object} [entry.metadata] Any metadata you want associated with the
   *     stored request. When requests are replayed you'll have access to this
   *     metadata object in case you need to modify the request beforehand.
   * @param {number} [entry.timestamp] The timestamp (Epoch time in
   *     milliseconds) when the request was first added to the queue. This is
   *     used along with `maxRetentionTime` to remove outdated requests. In
   *     general you don't need to set this value, as it's automatically set
   *     for you (defaulting to `Date.now()`), but you can update it if you
   *     don't want particular requests to expire.
   */
  async pushRequest(e) {
    await this._addRequest(e, "push");
  }
  /**
   * Stores the passed request in IndexedDB (with its timestamp and any
   * metadata) at the beginning of the queue.
   *
   * @param {QueueEntry} entry
   * @param {Request} entry.request The request to store in the queue.
   * @param {Object} [entry.metadata] Any metadata you want associated with the
   *     stored request. When requests are replayed you'll have access to this
   *     metadata object in case you need to modify the request beforehand.
   * @param {number} [entry.timestamp] The timestamp (Epoch time in
   *     milliseconds) when the request was first added to the queue. This is
   *     used along with `maxRetentionTime` to remove outdated requests. In
   *     general you don't need to set this value, as it's automatically set
   *     for you (defaulting to `Date.now()`), but you can update it if you
   *     don't want particular requests to expire.
   */
  async unshiftRequest(e) {
    await this._addRequest(e, "unshift");
  }
  /**
   * Removes and returns the last request in the queue (along with its
   * timestamp and any metadata). The returned object takes the form:
   * `{request, timestamp, metadata}`.
   *
   * @return {Promise<QueueEntry | undefined>}
   */
  async popRequest() {
    return this._removeRequest("pop");
  }
  /**
   * Removes and returns the first request in the queue (along with its
   * timestamp and any metadata). The returned object takes the form:
   * `{request, timestamp, metadata}`.
   *
   * @return {Promise<QueueEntry | undefined>}
   */
  async shiftRequest() {
    return this._removeRequest("shift");
  }
  /**
   * Returns all the entries that have not expired (per `maxRetentionTime`).
   * Any expired entries are removed from the queue.
   *
   * @return {Promise<Array<QueueEntry>>}
   */
  async getAll() {
    const e = await this._queueStore.getAll(), t = Date.now(), n = [];
    for (const a of e) {
      const r = this._maxRetentionTime * 60 * 1e3;
      t - a.timestamp > r ? await this._queueStore.deleteEntry(a.id) : n.push(Z(a));
    }
    return n;
  }
  /**
   * Returns the number of entries present in the queue.
   * Note that expired entries (per `maxRetentionTime`) are also included in this count.
   *
   * @return {Promise<number>}
   */
  async size() {
    return await this._queueStore.size();
  }
  /**
   * Adds the entry to the QueueStore and registers for a sync event.
   *
   * @param {Object} entry
   * @param {Request} entry.request
   * @param {Object} [entry.metadata]
   * @param {number} [entry.timestamp=Date.now()]
   * @param {string} operation ('push' or 'unshift')
   * @private
   */
  async _addRequest({ request: e, metadata: t, timestamp: n = Date.now() }, a) {
    const i = {
      requestData: (await x.fromRequest(e.clone())).toObject(),
      timestamp: n
    };
    switch (t && (i.metadata = t), a) {
      case "push":
        await this._queueStore.pushEntry(i);
        break;
      case "unshift":
        await this._queueStore.unshiftEntry(i);
        break;
    }
    this._syncInProgress ? this._requestsAddedDuringSync = !0 : await this.registerSync();
  }
  /**
   * Removes and returns the first or last (depending on `operation`) entry
   * from the QueueStore that's not older than the `maxRetentionTime`.
   *
   * @param {string} operation ('pop' or 'shift')
   * @return {Object|undefined}
   * @private
   */
  async _removeRequest(e) {
    const t = Date.now();
    let n;
    switch (e) {
      case "pop":
        n = await this._queueStore.popEntry();
        break;
      case "shift":
        n = await this._queueStore.shiftEntry();
        break;
    }
    if (n) {
      const a = this._maxRetentionTime * 60 * 1e3;
      return t - n.timestamp > a ? this._removeRequest(e) : Z(n);
    } else
      return;
  }
  /**
   * Loops through each request in the queue and attempts to re-fetch it.
   * If any request fails to re-fetch, it's put back in the same position in
   * the queue (which registers a retry for the next sync event).
   */
  async replayRequests() {
    let e;
    for (; e = await this.shiftRequest(); )
      try {
        await fetch(e.request.clone());
      } catch {
        throw await this.unshiftRequest(e), new l("queue-replay-failed", { name: this._name });
      }
  }
  /**
   * Registers a sync event with a tag unique to this instance.
   */
  async registerSync() {
    if ("sync" in self.registration && !this._forceSyncFallback)
      try {
        await self.registration.sync.register(`${X}:${this._name}`);
      } catch {
      }
  }
  /**
   * In sync-supporting browsers, this adds a listener for the sync event.
   * In non-sync-supporting browsers, or if _forceSyncFallback is true, this
   * will retry the queue on service worker startup.
   *
   * @private
   */
  _addSyncListener() {
    "sync" in self.registration && !this._forceSyncFallback ? self.addEventListener("sync", (e) => {
      if (e.tag === `${X}:${this._name}`) {
        const t = async () => {
          this._syncInProgress = !0;
          let n;
          try {
            await this._onSync({ queue: this });
          } catch (a) {
            if (a instanceof Error)
              throw n = a, n;
          } finally {
            this._requestsAddedDuringSync && !(n && !e.lastChance) && await this.registerSync(), this._syncInProgress = !1, this._requestsAddedDuringSync = !1;
          }
        };
        e.waitUntil(t());
      }
    }) : this._onSync({ queue: this });
  }
  /**
   * Returns the set of queue names. This is primarily used to reset the list
   * of queue names in tests.
   *
   * @return {Set<string>}
   *
   * @private
   */
  static get _queueNames() {
    return O;
  }
}
class ot {
  /**
   * @param {string} name See the {@link workbox-background-sync.Queue}
   *     documentation for parameter details.
   * @param {Object} [options] See the
   *     {@link workbox-background-sync.Queue} documentation for
   *     parameter details.
   */
  constructor(e, t) {
    this.fetchDidFail = async ({ request: n }) => {
      await this._queue.pushRequest({ request: n });
    }, this._queue = new it(e, t);
  }
}
const ct = "v2.0.1";
console.log("Service Worker Version:", ct);
const U = new ot("gearcargo-sync-queue", {
  maxRetentionTime: 24 * 60,
  // Retry for up to 24 hours (in minutes)
  onSync: async ({ queue: s }) => {
    let e;
    for (; e = await s.shiftRequest(); )
      try {
        const n = await fetch(e.request.clone()), a = await self.clients.matchAll();
        for (const r of a)
          r.postMessage({
            type: "SYNC_SUCCESS",
            url: e.request.url,
            method: e.request.method
          });
        console.log("Background sync successful:", e.request.url);
      } catch (n) {
        throw console.error("Background sync failed, re-queuing:", n), await s.unshiftRequest(e), n;
      }
    const t = await self.clients.matchAll();
    for (const n of t)
      n.postMessage({
        type: "SYNC_COMPLETE",
        message: "All offline changes have been synced"
      });
  }
});
ve([{"revision":"1bd3937dd4835c3b1e35840613296156","url":"offline.html"},{"revision":"a725446dc61e058ae105450a5d0493f3","url":"index.html"},{"revision":"8316116a0e97a31b3527c9f6be253f71","url":"favicon.ico"},{"revision":"8f6ef6502255573d01f7eb9174b35ad1","url":"icons/logo.png"},{"revision":null,"url":"assets/workbox-window.prod.es5-vqzQaGvo.js"},{"revision":null,"url":"assets/vendor-C9LfHnzx.js"},{"revision":null,"url":"assets/purify.es-B9ZVCkUG.js"},{"revision":null,"url":"assets/index.es-BQNg3RxQ.js"},{"revision":null,"url":"assets/index-ajT6s2P0.js"},{"revision":null,"url":"assets/index--FxaPVUw.css"},{"revision":null,"url":"assets/html2canvas.esm-CBrSDip1.js"},{"revision":null,"url":"assets/charts-zLA3yGA0.js"},{"revision":"8316116a0e97a31b3527c9f6be253f71","url":"favicon.ico"},{"revision":"8f6ef6502255573d01f7eb9174b35ad1","url":"icons/logo.png"},{"revision":"b4ba4b053d0fa57e3115071dd3c66823","url":"manifest.webmanifest"}]);
Ie();
const ht = Le("/index.html"), lt = new Me(ht, {
  denylist: [/^\/api/]
});
u(lt);
self.addEventListener("activate", (s) => {
  s.waitUntil(self.clients.claim());
});
u(
  ({ url: s }) => s.origin === "https://fonts.googleapis.com",
  new ae({
    cacheName: "google-fonts-stylesheets"
  })
);
u(
  ({ url: s }) => s.origin === "https://fonts.gstatic.com",
  new j({
    cacheName: "google-fonts-webfonts",
    plugins: [
      new q({
        statuses: [0, 200]
      }),
      new P({
        maxAgeSeconds: 60 * 60 * 24 * 365,
        // 1 year
        maxEntries: 30
      })
    ]
  })
);
u(
  ({ url: s }) => s.href.includes("material-icons") || s.href.includes("Material+Icons"),
  new j({
    cacheName: "material-icons",
    plugins: [
      new q({
        statuses: [0, 200]
      }),
      new P({
        maxAgeSeconds: 60 * 60 * 24 * 365,
        maxEntries: 10
      })
    ]
  })
);
u(
  ({ request: s }) => s.destination === "image",
  new j({
    cacheName: "images",
    plugins: [
      new q({
        statuses: [0, 200]
      }),
      new P({
        maxEntries: 100,
        maxAgeSeconds: 60 * 60 * 24 * 30
        // 30 days
      })
    ]
  })
);
u(
  ({ url: s, request: e }) => s.pathname.startsWith("/api/") && e.method === "GET",
  new Oe({
    cacheName: "api-cache",
    plugins: [
      new q({
        statuses: [0, 200]
      }),
      new P({
        maxEntries: 100,
        maxAgeSeconds: 60 * 60 * 24
        // 24 hours
      })
    ],
    networkTimeoutSeconds: 10
  })
);
u(
  ({ url: s, request: e }) => s.pathname.startsWith("/api/") && e.method === "POST",
  new S({
    plugins: [U]
  }),
  "POST"
);
u(
  ({ url: s, request: e }) => s.pathname.startsWith("/api/") && e.method === "PUT",
  new S({
    plugins: [U]
  }),
  "PUT"
);
u(
  ({ url: s, request: e }) => s.pathname.startsWith("/api/") && e.method === "PATCH",
  new S({
    plugins: [U]
  }),
  "PATCH"
);
u(
  ({ url: s, request: e }) => s.pathname.startsWith("/api/") && e.method === "DELETE",
  new S({
    plugins: [U]
  }),
  "DELETE"
);
u(
  ({ request: s }) => s.destination === "script" || s.destination === "style",
  new ae({
    cacheName: "static-resources"
  })
);
self.addEventListener("message", async (s) => {
  var e, t;
  if (s.data && s.data.type === "SKIP_WAITING" && self.skipWaiting(), s.data && s.data.type === "GET_PENDING_SYNC_COUNT")
    try {
      const r = (await ut()).transaction("requests", "readonly").objectStore("requests"), i = await new Promise((o, c) => {
        const h = r.count();
        h.onsuccess = () => o(h.result), h.onerror = () => c(h.error);
      });
      s.ports[0].postMessage({ count: i });
    } catch (n) {
      s.ports[0].postMessage({ count: 0, error: n.message });
    }
  if (s.data && s.data.type === "FORCE_SYNC")
    try {
      await self.registration.sync.register("workbox-background-sync:gearcargo-sync-queue"), (e = s.ports[0]) == null || e.postMessage({ success: !0 });
    } catch (n) {
      console.error("Manual sync registration failed:", n), (t = s.ports[0]) == null || t.postMessage({ success: !1, error: n.message });
    }
});
function ut() {
  return new Promise((s, e) => {
    const t = indexedDB.open("workbox-background-sync", 3);
    t.onerror = () => e(t.error), t.onsuccess = () => s(t.result);
  });
}
self.addEventListener("push", (s) => {
  if (!s.data) return;
  const e = s.data.json(), t = {
    body: e.body || "New notification",
    icon: "/icons/logo-192.png",
    badge: "/icons/logo-72.png",
    vibrate: [100, 50, 100],
    data: {
      url: e.url || "/"
    },
    actions: e.actions || [],
    tag: e.tag || "gearcargo-notification",
    renotify: !0
  };
  s.waitUntil(
    self.registration.showNotification(e.title || "GearCargo", t)
  );
});
self.addEventListener("notificationclick", (s) => {
  var t;
  s.notification.close();
  const e = ((t = s.notification.data) == null ? void 0 : t.url) || "/";
  s.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: !0 }).then((n) => {
      for (const a of n)
        if (a.url === e && "focus" in a)
          return a.focus();
      if (self.clients.openWindow)
        return self.clients.openWindow(e);
    })
  );
});
self.addEventListener("sync", (s) => {
  s.tag === "workbox-background-sync:gearcargo-sync-queue" && console.log("Background sync triggered for gearcargo-sync-queue");
});
console.log("GearCargo Service Worker loaded with Background Sync support");
