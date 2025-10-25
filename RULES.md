# Scrimmer of the Hill - Rules & Logic

## Overview
This bot tracks "King of the Hill" style scrimmage competitions where players compete to become and remain the king through consecutive wins.

## Core Game Rules

### Becoming King
- When **no king exists**, the winner of any game becomes the new king with a streak of 1
- When a **non-king defeats the current king**, they take the crown and start a new streak of 1
- The king role is automatically assigned/removed via Discord roles

### Defending the Crown
- When the **king wins against any player**, their streak increases by 1
- The king maintains their role and continues their streak
- Best streaks are tracked for leaderboard ranking

### Non-King Games
- Games between two non-king players **do not affect** king status or streaks
- These results do not need to be tracked but don't contribute to the leaderboard
- Only games involving the current king matter for streak tracking OR if there is no current king and the game results in the new king being crowned

### King Expiration
- If no games are played for **3 days**, the king is automatically dethroned
- The throne becomes vacant and the next winner becomes the new king
- Expired kings lose their role but their best streak is preserved

## Result Tracking

### Message Format
Results must be posted in the `#scrimmage-results` channel in this format:
```
@Player1 X-Y @Player2 (EGO)
```
Where:
- `@Player1` and `@Player2` are Discord user mentions
- `X-Y` is the score (higher score wins)
- `EGO` can be a single number (same ego for both) or `EGO1/EGO2` format
- Ties (X=Y) are ignored

### Ego Tracking

#### Current King's Ego Floor
- When a player becomes king, their ego at that moment becomes the **starting ego floor** for that streak
- As the king defends their crown, their **ego floor** is tracked as the **minimum ego** across all wins in that streak
- If the king wins with a lower ego than their current floor, the floor is updated to that lower value
- The ego floor represents the lowest difficulty level at which the king maintained their streak

#### Best Streak Ego
- Each player's **best historical streak** is associated with the **ego floor** from that specific streak
- When a player achieves a new personal best streak, the ego floor from that streak is saved
- If a player is on a different (non-record) streak, that streak's ego is only tracked internally
- The leaderboard displays ego values for both:
  1. **Current King Section**: Shows the active king's current streak and ego floor
  2. **Best Streaks Section**: Shows all-time best streaks with their associated ego floors

#### Example Scenarios
- Player becomes king at ego 90, defends at 88, then 92, then 85 → Ego floor = 85
- Player achieves 10-win streak (ego floor 85), later gets 8-win streak (ego floor 90) → Leaderboard shows 10 wins with ego 85
- Current king with 5-win streak (ego floor 92) appears on leaderboard with ego 92 next to crown 👑

### Multiple Results
- Multiple results can be posted in a single message (one per line)
- Each result is processed independently in order

## Edit Handling Logic

### Three Edit Scenarios

#### 1. Ego Change Only
**Scenario**: User fixes a typo in ego values (e.g., `(80/90)` → `(80/95)`)

**Behavior**:
- **No changes occur** - ego edits on existing results are ignored
- The original ego values used when the game was first processed remain
- Message is marked as reprocessed with updated content hash
- This prevents retroactive changes to historical ego floors

**Rationale**: Ego floors represent the actual difficulty at the time of play. Allowing retroactive changes would invalidate streak achievements.

**Log Output**: `"Reprocessing EXISTING result: Winner=X (ego Y)"`

#### 2. Winner Change
**Scenario**: User corrects the score, changing who won (e.g., `5-3` → `3-5`)

**Behavior**:
- If the message is **recent** (last 5 messages in channel):
  - Winner change is detected
  - Bot fetches last 5 messages and recalculates streaks from them **starting fresh**
  - Assumes no king existed before these 5 messages (streak starts at 0)
  - King role and current streak are updated based on recalculated history
  - **Best streaks are preserved** (never decreased)
  - Log: `"Winner changed in recent message - recalculating from last 5 messages"`
  
- If the message is **old** (beyond last 5 messages):
  - Winner change is detected
  - Edit is **ignored** (treated as already processed)
  - Log: `"Winner changed in old message - ignoring edit, beyond threshold"`

**Important Limitation**: 
- Recalculation treats the last 5 messages as a fresh start
- If someone had a long streak before those 5 messages, that context is lost during recalculation
- However, their **best streak** is always preserved in the leaderboard
- Current king/streak may change, but historical achievements remain
- This trade-off keeps implementation simple while catching immediate errors

**Rationale**: 
- Recalculating only last 5 messages is cheap and fast
- Catches immediate mistakes without expensive full history processing
- Old history remains immutable for stability
- Best streaks never decrease, so historical achievements are safe

#### 3. Content Unchanged
**Scenario**: Message edited but content is identical (whitespace only, etc.)

**Behavior**:
- Content hash matches previous processing
- Message is skipped entirely
- No processing occurs

**Log Output**: `"Message already processed with same content, skipping"`

## Result Deduplication

### Result Keys
Each game result is tracked using a unique key:
```
{message_id}:{player1_id}:{player2_id}:{timestamp}
```
Where `player1_id` and `player2_id` are **sorted numerically** to ensure the same game is recognized regardless of player order.

### Stored Data
The bot maintains a dictionary mapping result keys to winner IDs:
```python
processed_results = {
    "123456:111:222:1698765432": 111,  # Player 111 won
    "123457:111:333:1698765500": 333   # Player 333 won
}
```

### Detection Logic
1. Parse edited message to extract results
2. Generate result key for each game
3. Compare current winner to stored winner_id
4. If different (and not 0), trigger full recalculation

## State Persistence

### Leaderboard Message
- Posted and pinned in `#scrimmer-of-the-hill` channel
- Contains visible leaderboard with rankings
- Embeds complete state as JSON in spoiler tags
- Updated after every game or edit

### State Data
The following data is persisted:
- `best_streaks`: Dictionary of user_id → highest streak achieved
- `best_streak_egos`: Dictionary of user_id → ego floor from their best streak
- `current_king_id`: User ID of current king (or null)
- `current_streak`: Current king's active streak count
- `current_king_ego_floor`: Minimum ego during current king's active streak
- `last_activity`: Timestamp of most recent game
- `processed_messages`: Dictionary of message_id → content_hash
- `processed_results`: Dictionary of result_key → winner_id

### Recovery on Restart
- Bot searches for pinned message in leaderboard channel
- Extracts JSON state from spoiler block
- Restores all tracked data
- Continues operation seamlessly

## Message Processing Flow

```
New/Edited Message
    ↓
Is bot's own message? → Skip
    ↓
In #scrimmage-results? → Skip if not
    ↓
Calculate content hash
    ↓
Already processed with same hash? → Skip
    ↓
Check if king expired (3 days) → Dethrone if expired
    ↓
Parse results from message
    ↓
Check if winner changed:
    - If no: Process normally (update ego if existing result)
    - If yes AND message is recent (last 5): Recalculate from last 5 messages
    - If yes AND message is old: Log warning, skip edit
    ↓
Process each result (if no winner change or after recalculation):
    - Determine winner/loser
    - Update ego values (always)
    - Check if new result
    - If new: Update streaks, assign roles
    - If existing: Skip streak updates
    ↓
Mark message as processed
    ↓
Update leaderboard message
```

## Leaderboard Display

### Ranking Criteria
Players are ranked by their **best streak** (highest consecutive wins as king)

### Display Format
```
🏆 Scrim Leaderboard

**Current King** 👑
@Player1 - 5 wins (Ego: 92)

**Best Streaks**
1. @Player2 - 15 wins (Ego: 85)
2. @Player1 - 12 wins (Ego: 88)
3. @Player3 - 8 wins (Ego: 90)
...

Last game: 5 minutes ago
King expires: in 2 days

||```json
{state data}
```||
```

### Display Sections
- **Current King**: Shown at the top if a king exists, displays their active streak and current ego floor
- **Best Streaks**: Ranked list of all-time best streaks with their historical ego floors
- The current king may appear in both sections if their current streak is also their best

## Error Handling

### Missing Members
- If a mentioned user is not found in the guild, the result is skipped
- Error logged: `"Could not find members (winner=X, loser=Y)"`

### Permission Errors
- If bot lacks permission to assign/remove roles, operation is skipped
- Error logged: `"Bot lacks permission to..."`
- Game is still tracked, role assignment retried on next result

### Invalid Messages
- Messages that don't match the result pattern are ignored
- No error logged (silent skip)
- Bot only processes valid result formats

## Technical Notes

### Timezone Handling
- All timestamps stored as UTC
- Message `created_at` used for game timestamp (not processing time)
- Ensures chronological ordering during recalculation

### Memory Management
- `processed_messages` and `processed_results` only track last 5 messages
- When processing new results, old unneeded entries are pruned
- Minimal memory footprint - typically 5-10 tracked results
- During recalculation, historical streak context is discarded (starts fresh)
- Best streaks are never pruned or decreased

### Performance Considerations
- Winner-change edits on recent messages trigger limited recalculation (last 5 messages only)
- Winner-change edits on old messages are ignored (history locked beyond threshold)
- Ego-only edits are fast (no recalculation needed)
- Recalculation is bounded and predictable (max 5 messages)
