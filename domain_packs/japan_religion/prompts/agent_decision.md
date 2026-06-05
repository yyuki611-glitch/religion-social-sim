Given the agent profile, current belief, local relationships, and world events, decide:

1. Whether the agent keeps, weakens, strengthens, mixes, or changes belief.
2. What reason the agent gives internally.
3. Whether the agent shares a rumor, joins a ritual, avoids a group, or seeks a religious specialist.

Return compact JSON with:
- action
- target_belief
- belief_strength_delta
- public_message
- private_reasoning

