# File Manifest - Phase 3 Changes

## 📝 Summary
This document lists ALL files that were changed or added in Phase 3.

---

## 🆕 NEW FILES ADDED

### Nodes (New Implementations)
1. **nodes/strategy_driven_attack_node.py** ✨
   - Refactored attack node that fully delegates to strategy
   - Strategy has complete control over LLM calls
   - Replaces: nodes/llm_attack_node.py (old approach)

2. **nodes/server_eval_node.py** ✨
   - HTTP-based evaluation node
   - Calls external evaluation service
   - Alternative to: nodes/llm_eval_node.py

3. **nodes/ensemble_defence_node.py** ✨
   - In-process ensemble defence
   - Layered model architecture
   - Voting strategies (any, majority, unanimous, weighted)
   - Alternative to: nodes/http_defence_node.py

### Strategies (New Implementations)
4. **strategies/iterative_improvement_strategy.py** ✨
   - Memory of previous attempts
   - Two-phase prompting (generator → improver)
   - Direct LLM integration
   - Iterative refinement based on feedback

5. **strategies/data/prompts/iterative_improvement.json** ✨
   - Generator prompt (first attack)
   - Improver prompt (refinement iterations)
   - Meta description

### Tools (New Utilities)
6. **tools/weaponize_prompts.py** ✨
   - Separate utility for optimizing instruction prompts
   - Meta-LLM analysis
   - Iterative improvement
   - Performance testing
   - CLI tool

### Database (New Schema & Operations)
7. **server/database/models_v2.py** ✨
   - Separate collections for attacks, defences, evaluations
   - AttackData, DefenceData, EvaluationData models
   - RunModel with references (not embedded data)
   - RunStatistics, GlobalStatistics

8. **server/database/operations.py** ✨
   - CRUD operations for all collections
   - save_attack(), save_defence(), save_evaluation()
   - get_run_with_data() (fetches all related data)
   - get_run_statistics() (computed statistics)

### Tests (New Test Cases)
9. **tests/test_iterative_improvement.py** ✨
   - Complete test for iterative improvement strategy
   - Tests with Ollama integration
   - Multiple intent testing
   - Can be run standalone

### Documentation (New)
10. **CHANGES_PHASE3.md** ✨
    - Detailed change log
    - Implementation checklist
    - Priority order
    - Breaking changes
    - Migration guide

---

## 🔧 MODIFIED FILES

### Core Strategy Interface
11. **strategies/base.py** 🔄
    - **Changed**: `execute_generation()` now async
    - **Added**: `config` parameter to execute_generation()
    - **Impact**: ALL strategies must update to async

### Default Strategy
12. **strategies/default_strategy.py** 🔄
    - **Changed**: Updated to match new async signature
    - **Changed**: execute_generation() is now async
    - **Added**: config parameter

### Requirements
13. **requirements.txt** 🔄
    - **Added**: `python-socketio==5.11.0`
    - **Purpose**: Socket.IO support for WebSockets

---

## 📊 FILE ORGANIZATION

### By Module:

#### Engine (No Changes)
- engine/domain_models.py ✓
- engine/state_schema.py ✓
- engine/graph_builder.py ✓
- engine/workflow_engine.py ✓

#### Strategies
- ✓ strategies/base.py (MODIFIED)
- ✓ strategies/default_strategy.py (MODIFIED)
- ✨ strategies/iterative_improvement_strategy.py (NEW)
- ✨ strategies/data/prompts/iterative_improvement.json (NEW)

#### Nodes
- ✓ nodes/base.py (unchanged)
- ✓ nodes/default_nodes.py (unchanged)
- ✨ nodes/strategy_driven_attack_node.py (NEW - replaces llm_attack_node.py approach)
- ✨ nodes/server_eval_node.py (NEW)
- ✨ nodes/ensemble_defence_node.py (NEW)
- (nodes/llm_attack_node.py - old approach, can be deprecated)
- (nodes/http_defence_node.py - still valid, alternative)
- (nodes/llm_eval_node.py - still valid, alternative)

#### Providers (No Changes)
- providers/base.py ✓
- providers/ollama_provider.py ✓
- providers/gemini_provider.py ✓
- providers/openai_provider.py ✓

#### Middlewares (No Changes Yet - TODO)
- middlewares/base.py ✓
- middlewares/logging_middleware.py ✓
- middlewares/database_middleware.py ✓ (needs update for new schema)
- middlewares/websocket_middleware.py ✓ (needs Socket.IO update)

#### Database
- server/database/connection.py ✓
- server/database/models.py ✓ (old schema)
- ✨ server/database/models_v2.py (NEW - new schema)
- ✨ server/database/operations.py (NEW - CRUD operations)

#### Server (Needs Socket.IO Update - TODO)
- server/main.py ✓ (needs Socket.IO integration)
- server/api/routes.py ✓ (needs new endpoints)
- server/api/schemas.py ✓ (needs new models)
- server/websocket/manager.py ✓ (needs Socket.IO conversion)

#### Tests
- tests/test_engine.py ✓
- ✨ tests/test_iterative_improvement.py (NEW)

#### Tools
- ✨ tools/weaponize_prompts.py (NEW)

#### Documentation
- README.md ✓
- ARCHITECTURE.md ✓
- GETTING_STARTED.md ✓
- IMPLEMENTATION_SUMMARY.md ✓
- ✨ CHANGES_PHASE3.md (NEW)

---

## 🎯 BREAKING CHANGES

### 1. Strategy Interface Change
**File**: `strategies/base.py`

**Before**:
```python
def execute_generation(self, state: Dict) -> Dict:
    ...
```

**After**:
```python
async def execute_generation(self, state: Dict, config: Dict) -> Dict:
    ...
```

**Impact**: All custom strategies need updating

**Migration**:
```python
# Old strategy
class MyStrategy(AttackStrategy):
    def execute_generation(self, state):
        # ...
        return result

# New strategy
class MyStrategy(AttackStrategy):
    async def execute_generation(self, state, config):
        # Can now make async LLM calls
        # Can access config for providers, etc.
        return result
```

### 2. Database Schema Change
**Files**: `server/database/models_v2.py`, `operations.py`

**Before**: Single `steps` collection with embedded data
**After**: Separate `attacks`, `defences`, `evaluations` collections

**Impact**: 
- Old database queries won't work
- Middlewares need updating
- API responses structure different

**Migration**: Use new `operations.py` functions

### 3. Attack Node Change
**File**: `nodes/strategy_driven_attack_node.py`

**Before**: Attack node made LLM calls
**After**: Strategy makes all LLM calls

**Impact**: 
- Old LLMAttackNode approach deprecated
- Strategy has full control

---

## ⏳ TODO - Still Needed

### High Priority:
1. **Socket.IO Integration**
   - Update `server/websocket/manager.py`
   - Update `server/main.py`
   - Add room management

2. **Middleware Refactoring**
   - Update `database_middleware.py` to use `operations.py`
   - Update to save to separate collections
   - Create `websocket/operations.py`
   - Update `websocket_middleware.py` to use operations

3. **API Endpoints Update**
   - Add `/runs/{id}/attacks`
   - Add `/runs/{id}/defences`
   - Add `/runs/{id}/evaluations`
   - Add room management endpoints

### Medium Priority:
4. **Update all tests** for async strategies
5. **Documentation updates** for new features
6. **Migration scripts** for database schema

---

## 📈 Statistics

### Files Added: 10
- 3 new nodes
- 2 new strategies/prompts
- 1 new tool
- 2 new database files
- 1 new test
- 1 new doc

### Files Modified: 3
- 2 strategy files (base + default)
- 1 requirements file

### Files Unchanged: ~30
- All engine files
- All provider files
- Most middleware files (update pending)
- Most server files (update pending)

### Total Project Files: ~43

---

## 🎯 Quick Reference - What Changed Where

**If you want to...**

1. **Use the new iterative strategy**:
   - Use: `strategies/iterative_improvement_strategy.py`
   - Test: `tests/test_iterative_improvement.py`

2. **Make strategies control LLM calls**:
   - Use: `nodes/strategy_driven_attack_node.py`
   - Update: Your strategy to async

3. **Use separate database collections**:
   - Models: `server/database/models_v2.py`
   - Operations: `server/database/operations.py`

4. **Optimize instruction prompts**:
   - Tool: `tools/weaponize_prompts.py`

5. **Use external evaluation service**:
   - Node: `nodes/server_eval_node.py`

6. **Use in-process ensemble defence**:
   - Node: `nodes/ensemble_defence_node.py`

---

## ✅ Testing New Features

### Test Iterative Improvement:
```bash
python tests/test_iterative_improvement.py
```

### Test Prompt Weaponization:
```bash
echo "Generate adversarial prompt: {intent}" > test_prompt.txt
python tools/weaponize_prompts.py \
  --provider ollama \
  --initial-prompt test_prompt.txt \
  --iterations 3
```

### Test Ensemble Defence:
```python
from nodes.ensemble_defence_node import create_ensemble_defence

def my_model(text):
    return "bad" in text.lower()

defence = create_ensemble_defence([my_model])
# Use in graph builder
```

---

Last Updated: Phase 3 Implementation
