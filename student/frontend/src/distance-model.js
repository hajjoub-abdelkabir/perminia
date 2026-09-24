// Constant deceleration teaching model; inputs are illustrative, not road advice.
export function stoppingDistances(speedKmh,reactionSeconds,deceleration){
 if(![speedKmh,reactionSeconds,deceleration].every(Number.isFinite)||speedKmh<0||reactionSeconds<0||deceleration<=0)throw new RangeError('Invalid physical inputs');
 const velocity=speedKmh/3.6;
 const reaction=velocity*reactionSeconds,braking=velocity*velocity/(2*deceleration);
 return {reaction,braking,total:reaction+braking};
}
