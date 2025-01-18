# Scope
- is a lifespan of a dependency;
- is required almost for each `Provider`;
- in frameworks' integrations some scopes are entered automatically;
- dependencies of `Resource` and `Singleton` provider cached for the lifespan of its scope;

## Default scopes:
1. `APP`:
   - tied to the entire application lifetime;
   - can be used for singletons of `Resource` and `Singleton` providers;
   - must be managed manually in lifecycle methods of the application: see `integrations` section;
2. `SESSION`:
   - for websocket session lifetime;
   - dependencies of this scope cannot be used for http-requests;
   - managed automatically;
3. `REQUEST`:
   - for dependencies which are created for each user request, for example database session;
   - managed automatically for http-request;
   - must be managed manually for websockets;
4. `ACTION`:
   - for lifetime less than request;
   - must be managed manually;
5. `STEP`:
   - for lifetime less than `ACTION`;
   - must be managed manually.
