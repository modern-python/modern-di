# Development Notes
## Base parts
### Scope
- any int enum, starting from 1 with step 1

### Container
- stateful
- contains resolved dependencies
- contains context stacks to finalize
- if scope is not the first than must have parent `Container`

### Resolvers
- stateless
- build dependency and save it to `Container`
- if dependency is already saved or overridden in `Container`, returns it
- can have dependencies only the same or lower scope, check in init

### Graph
- Cannot be instantiated
- Contains graph of `Resolvers`
- Can initialize its resources

### Questions
1. Thread-safety
2. Configuration without global object
