export function remainingSeconds(deadline, now) {
  return Math.max(0, Math.ceil((deadline - now) / 1000));
}
export function settleQuestion(action, choices, now, deadline) {
  if (now >= deadline || action === 'timeout') return { status: 'expired', choices: [] };
  if (action === 'confirm' && choices.length) return { status: 'answered', choices: [...choices] };
  return { status: 'skipped', choices: [] };
}
