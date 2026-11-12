#!/bin/bash
# Quick sanity check against the running mlx_lm.server.
# Usage: ./scripts/test_server.sh "Show my pending visits yesterday"

PROMPT="${1:-Show my pending visits yesterday}"

curl -s http://localhost:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d "{
    \"messages\": [
      {\"role\": \"system\", \"content\": \"You are an HR application assistant for TalentLink's Activities module. Available actions: get_visits, get_tasks, get_main_activities, get_dashboard. statusId: 1 Pending, 2 In progress, 3 Cancelled, 4 Completed, 5 Rejected, 7 Partially completed. priorityId: 1 low, 2 medium, 3 high. scope: all, my_team, my_activities, private. Never invent a value for a field the user didn't mention. You can only read/search activities — you cannot create, edit, delete, approve, reschedule, or change the status of anything. Always reply with ONLY this JSON shape: {\\\"action\\\": null, \\\"arguments\\\": null, \\\"needs_clarification\\\": false, \\\"clarification_question\\\": null, \\\"refused\\\": false, \\\"refusal_reason\\\": null}. Fill action/arguments when you have enough info. Set needs_clarification true and fill clarification_question when required info (at least a date range) is missing. Set refused true and fill refusal_reason for anything outside reading activities. Reply in the user's language for questions/refusals; keep field names and values in English.\"},
      {\"role\": \"user\", \"content\": \"$PROMPT\"}
    ],
    \"temperature\": 0.1
  }" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['choices'][0]['message']['content'])"
