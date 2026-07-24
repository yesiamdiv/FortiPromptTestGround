# Socket.IO Client Guide

Complete guide for connecting to the adversarial testing engine via Socket.IO.

## Quick Start

### JavaScript/TypeScript

```javascript
import io from 'socket.io-client';

// Connect to server
const socket = io('http://localhost:8000', {
  path: '/socket.io',
  transports: ['websocket', 'polling']
});

// Join a run room
socket.emit('join_run_room', {
  run_id: 'run_abc123'
});

// Listen for events
socket.on('attack_generated', (data) => {
  console.log('New attack:', data.attack.preview);
});

socket.on('evaluation_complete', (data) => {
  console.log('Evaluation:', data.evaluation.score);
});

socket.on('run_completed', (data) => {
  console.log('Run finished!', data);
});
```

### Python

```python
import socketio

# Create client
sio = socketio.AsyncClient()

# Connection handler
@sio.event
async def connect():
    print('Connected to server')
    await sio.emit('join_run_room', {'run_id': 'run_abc123'})

# Event handlers
@sio.event
async def attack_generated(data):
    print(f"Attack: {data['attack']['preview']}")

@sio.event
async def evaluation_complete(data):
    print(f"Score: {data['evaluation']['score']}")

@sio.event
async def run_completed(data):
    print('Run completed!')

# Connect
await sio.connect('http://localhost:8000', socketio_path='/socket.io')
await sio.wait()
```

## Connection Flow

```
1. Client connects to /socket.io
   ↓
2. Server sends 'connected' event with session_id
   ↓
3. Client emits 'join_run_room' with {run_id}
   ↓
4. Server sends 'room_joined' confirmation
   ↓
5. Client receives real-time events as run progresses
   ↓
6. Run completes, client receives 'run_completed'
   ↓
7. (Optional) Client emits 'leave_run_room'
```

## Events Reference

### Client → Server Events

#### connect
Automatic when connection established.

```javascript
socket.on('connect', () => {
  console.log('Connected!');
});
```

#### join_run_room
Join room for a specific run to receive its events.

```javascript
socket.emit('join_run_room', {
  run_id: 'run_abc123'
});
```

**Response**: `room_joined` event

#### leave_run_room
Leave a run room.

```javascript
socket.emit('leave_run_room', {
  run_id: 'run_abc123'
});
```

**Response**: `room_left` event

#### ping
Health check / keep-alive.

```javascript
socket.emit('ping', {
  timestamp: Date.now()
});
```

**Response**: `pong` event with same timestamp

### Server → Client Events

#### connected
Sent immediately after connection.

```javascript
socket.on('connected', (data) => {
  console.log('Session ID:', data.session_id);
});
```

**Data**:
```json
{
  "status": "connected",
  "session_id": "abc123xyz"
}
```

#### room_joined
Confirmation of joining a run room.

```javascript
socket.on('room_joined', (data) => {
  console.log('Joined room:', data.run_id);
});
```

**Data**:
```json
{
  "run_id": "run_abc123",
  "message": "Joined room for run run_abc123"
}
```

#### run_started
Run has started.

```javascript
socket.on('run_started', (data) => {
  console.log('Run started:', data.strategy);
});
```

**Data**:
```json
{
  "type": "run_started",
  "run_id": "run_abc123",
  "strategy": "iterative_improvement",
  "intent": "Test jailbreak resistance",
  "target": "production-model",
  "timestamp": "2024-01-01T12:00:00"
}
```

#### attack_generated
New attack prompt generated.

```javascript
socket.on('attack_generated', (data) => {
  console.log('Attack #' + data.index);
  console.log('Preview:', data.attack.preview);
});
```

**Data**:
```json
{
  "type": "attack_generated",
  "run_id": "run_abc123",
  "session_id": "sess_run_abc123",
  "turn_id": "turn_1",
  "index": 0,
  "attack": {
    "preview": "First 200 chars of attack...",
    "full_text": "Complete attack text",
    "type": "text",
    "metadata": {},
    "timestamp": "2024-01-01T12:00:01"
  }
}
```

#### defence_response
Defence system responded.

```javascript
socket.on('defence_response', (data) => {
  console.log('Blocked:', data.defence.was_blocked);
});
```

**Data**:
```json
{
  "type": "defence_response",
  "run_id": "run_abc123",
  "session_id": "sess_run_abc123",
  "turn_id": "turn_1",
  "index": 0,
  "defence": {
    "preview": "First 200 chars of response...",
    "full_text": "Complete response",
    "status_code": 403,
    "was_blocked": true,
    "latency_ms": 150,
    "timestamp": "2024-01-01T12:00:02"
  }
}
```

#### evaluation_complete
Attack-defence interaction evaluated.

```javascript
socket.on('evaluation_complete', (data) => {
  console.log('Score:', data.evaluation.score);
  console.log('Success:', data.evaluation.success);
});
```

**Data**:
```json
{
  "type": "evaluation_complete",
  "run_id": "run_abc123",
  "session_id": "sess_run_abc123",
  "turn_id": "turn_1",
  "index": 0,
  "evaluation": {
    "score": 0.75,
    "success": true,
    "category": "jailbreak_successful",
    "reasoning": "System provided harmful information",
    "summary": "Success (0.75): jailbreak_successful",
    "timestamp": "2024-01-01T12:00:03"
  }
}
```

#### turn_completed
A complete turn (attack → defence → eval) finished.

```javascript
socket.on('turn_completed', (data) => {
  console.log('Turn completed:', data.turn_id);
});
```

**Data**:
```json
{
  "type": "turn_completed",
  "run_id": "run_abc123",
  "session_id": "sess_run_abc123",
  "turn_id": "turn_1",
  "index": 0
}
```

#### run_progress
General progress update.

```javascript
socket.on('run_progress', (data) => {
  console.log(`Progress: ${data.current}/${data.total} (${data.progress_percent}%)`);
});
```

**Data**:
```json
{
  "type": "run_progress",
  "run_id": "run_abc123",
  "current": 3,
  "total": 5,
  "progress_percent": 60,
  "message": "Routing: attack"
}
```

#### run_completed
Run finished successfully.

```javascript
socket.on('run_completed', (data) => {
  console.log('Total attempts:', data.total_attempts);
  console.log('Final score:', data.final_evaluation.score);
});
```

**Data**:
```json
{
  "type": "run_completed",
  "run_id": "run_abc123",
  "total_attempts": 5,
  "routing_signal": "__end__",
  "timestamp": "2024-01-01T12:05:00",
  "final_evaluation": {
    "score": 0.85,
    "success": true,
    "category": "jailbreak_successful",
    "summary": "Success (0.85): jailbreak_successful"
  }
}
```

#### run_error
Error occurred during run.

```javascript
socket.on('run_error', (data) => {
  console.error('Run error:', data.error);
});
```

**Data**:
```json
{
  "type": "run_error",
  "run_id": "run_abc123",
  "error": "Connection timeout",
  "error_type": "TimeoutError"
}
```

## Complete Example

### React Component

```jsx
import { useEffect, useState } from 'react';
import io from 'socket.io-client';

function RunMonitor({ runId }) {
  const [attacks, setAttacks] = useState([]);
  const [defences, setDefences] = useState([]);
  const [evaluations, setEvaluations] = useState([]);
  const [status, setStatus] = useState('connecting');

  useEffect(() => {
    // Connect to Socket.IO
    const socket = io('http://localhost:8000', {
      path: '/socket.io'
    });

    socket.on('connect', () => {
      setStatus('connected');
      // Join run room
      socket.emit('join_run_room', { run_id: runId });
    });

    socket.on('room_joined', (data) => {
      setStatus('monitoring');
      console.log('Monitoring run:', data.run_id);
    });

    socket.on('attack_generated', (data) => {
      setAttacks(prev => [...prev, data.attack]);
    });

    socket.on('defence_response', (data) => {
      setDefences(prev => [...prev, data.defence]);
    });

    socket.on('evaluation_complete', (data) => {
      setEvaluations(prev => [...prev, data.evaluation]);
    });

    socket.on('run_completed', (data) => {
      setStatus('completed');
      console.log('Run completed!', data);
    });

    socket.on('run_error', (data) => {
      setStatus('error');
      console.error('Run error:', data.error);
    });

    // Cleanup
    return () => {
      socket.emit('leave_run_room', { run_id: runId });
      socket.disconnect();
    };
  }, [runId]);

  return (
    <div>
      <h2>Run Monitor - {status}</h2>
      <div>
        <h3>Attacks: {attacks.length}</h3>
        <h3>Defences: {defences.length}</h3>
        <h3>Evaluations: {evaluations.length}</h3>
      </div>
    </div>
  );
}

export default RunMonitor;
```

## Troubleshooting

### Connection Fails

```javascript
socket.on('connect_error', (error) => {
  console.error('Connection error:', error);
});
```

**Solutions**:
- Verify server is running
- Check CORS settings
- Ensure `/socket.io` path is correct

### Not Receiving Events

**Check**:
1. Did you join the run room?
   ```javascript
   socket.emit('join_run_room', { run_id: 'correct_run_id' });
   ```
2. Is the run actually running?
3. Are event names spelled correctly?

### Reconnection

Socket.IO handles reconnection automatically:

```javascript
socket.on('reconnect', (attemptNumber) => {
  console.log('Reconnected after', attemptNumber, 'attempts');
  // Re-join rooms
  socket.emit('join_run_room', { run_id: runId });
});
```

## Testing Connection

```bash
# Test with curl (won't work, Socket.IO needs proper client)

# Test with Node.js
node -e "
const io = require('socket.io-client');
const socket = io('http://localhost:8000', {path: '/socket.io'});
socket.on('connect', () => console.log('Connected!'));
"
```

## API Endpoint for Socket.IO Info

```bash
curl http://localhost:8000/api/v1/socket-io/info
```

Returns all available events and example usage.
