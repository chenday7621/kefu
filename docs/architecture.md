# Architecture

Official user simulator → official orchestrator → KefuTau2Agent → provider-native
structured calls → Kefu ToolRegistry validation → official environment execution
→ official observation → Kefu next decision. Official scorer evaluates the trajectory.

`build_kefu_agent_factory` implements the official half-duplex interface, not
LLMAgent decisions. AgentIdentityMonitor blocks that official decision entry point
and counts actual Kefu decisions, validations and live environment results.
The guard is serial and process-scoped; concurrency must remain 1.

The standalone ToolLoop is a separate internal-executor utility. The certified
Retail runtime uses external execution through the official orchestrator, so tools
are not run twice. No planner, reflection or second agent has been added.

Six runtime files are byte-identical to the internal checkpoint; SOURCE_PROVENANCE.json
provides the mapping. Public packaging and offline metric utilities are new wrappers,
not a new certified 40-task run. No business logic or prompt was edited.
