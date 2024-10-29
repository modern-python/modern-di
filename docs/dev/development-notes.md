# Development Notes
## Base parts
### Scope
- any int enum, starting from 1 with step 1

### Container
- all states live in containers:
  - resolved dependencies
  - context stacks for resources
  - overrides

### Resolvers
- completely stateless
- if dependency is already saved or overridden in `Container`, returns it
- otherwise build dependency and save it to `Container`
- can have dependencies only the same or lower scope, check in init

### Graph
- Cannot be instantiated
- Contains graph of `Resolvers`
- Can initialize its resources and factories to container

### Questions
1. Thread-safety
2. Configuration without global object
