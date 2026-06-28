-- RaceSync CSP Lua phantoms — Tier-B injection STARTER (see specs/13)
--
-- Reads the fixed-layout phantom frame written by the RaceSync shared-memory bridge
-- (`python -m racesync.cli ac-bridge --file racesync_phantoms.bin`) and moves N phantom
-- car meshes to the real field's positions each frame.
--
-- THIS IS A STARTER SKELETON, not a finished script. Two things must be wired against the
-- live acc-lua-sdk when you have AC + CSP open (marked TODO below):
--   1. Reading the mmap file (CSP Lua shared-memory / struct API).
--   2. Spawning + transforming car meshes (use the acc-lua-internal `traffic` tool as the
--      reference: low-LOD body on a 'BODY' node that you reposition each frame).
-- And one calibration step: the affine transform from RaceSync track-plane metres to AC
-- world coordinates (specs/13 §13.4 Step 2).
--
-- Binary frame layout (must match src/racesync/injection/shm_bridge.py):
--   Header  <4sHHII> : magic "RSPH", version u16, count u16, flags u32, seq u32   (16 bytes)
--   Record  <I5f>    : car_num u32, x f32, y f32, heading f32, speed f32, quality f32 (24 bytes)
--   MAX_CARS = 64
--   flags: bit0 = CODE 60, bit1 = CHEQUERED

local FRAME_FILE = 'racesync_phantoms.bin'
local MAX_CARS = 64
local HEADER_SIZE = 16
local RECORD_SIZE = 24

-- Collision (specs/13 §13.9). Phantoms can be made collidable via CSP Lua physics rigid
-- bodies (kinetic: they push the player but are not pushed back — the correct model, since
-- the real car never felt the contact). Gate it on data quality so contact is only solid
-- when the fix is RTK-grade and fresh; otherwise the phantom is a pass-through ghost.
local COLLIDABLE = false           -- start false; enable after RTK fidelity is validated
local COLLIDE_QUALITY_MIN = 0.9    -- quality >= this -> solid; below -> ghost
local CAR_BOX = { 4.5, 1.2, 1.9 }  -- collider size in metres (length, height, width)

-- Calibration: RaceSync (x, y) metres -> AC world (x, z). Replace with values solved in
-- Step 2 (scale, rotation theta, translation). Identity until calibrated.
local CAL = { scale = 1.0, theta = 0.0, tx = 0.0, tz = 0.0 }

local function racesync_to_ac(x, y)
  local c, s = math.cos(CAL.theta), math.sin(CAL.theta)
  local ax = CAL.scale * (c * x - s * y) + CAL.tx
  local az = CAL.scale * (s * x + c * y) + CAL.tz
  return ax, az
end

local phantoms = {}   -- car_num -> { mesh = ..., x = , z = , heading = }
local last_seq = -1

-- TODO(acc-lua-sdk): open the mmap frame file for reading. CSP exposes shared-memory /
-- file reads; confirm the exact API (e.g. ac.readMemoryMappedFile / io). Return raw bytes.
local function read_frame()
  -- placeholder: return nil until wired
  return nil
end

-- Minimal little-endian unpackers (CSP Lua ships a 'string.unpack'-style API; prefer it).
local function u16(b, o) return b:byte(o) + b:byte(o + 1) * 256 end
local function u32(b, o)
  return b:byte(o) + b:byte(o + 1) * 256 + b:byte(o + 2) * 65536 + b:byte(o + 3) * 16777216
end
-- f32 decode omitted for brevity — use string.unpack('<f', ...) from CSP Lua.

local function parse_and_apply(bytes)
  if bytes == nil then return end
  local count = u16(bytes, 7)          -- offset of 'count' in the header (1-based Lua)
  local flags = u32(bytes, 9)
  local seq = u32(bytes, 13)
  if seq == last_seq then return end   -- no new frame
  last_seq = seq

  local code60 = (flags % 2) >= 1
  for i = 0, math.min(count, MAX_CARS) - 1 do
    local o = HEADER_SIZE + i * RECORD_SIZE + 1
    local car_num = u32(bytes, o)
    -- TODO: decode x, y, heading, speed, quality with string.unpack('<I4f4f4f4f4f', ...)
    local x, y, heading = 0.0, 0.0, 0.0
    local ax, az = racesync_to_ac(x, y)

    -- TODO: decode quality (last float in the record) for the collision gate below.
    local quality = 1.0

    local p = phantoms[car_num]
    if p == nil then
      -- TODO(acc-lua-internal/traffic): spawn a low-LOD car mesh with a 'BODY' node.
      -- TODO(collision, acc-lua-sdk ac_physics): if COLLIDABLE, create a KINETIC rigid body
      --   for this phantom with a box collider CAR_BOX (kinetic = impacts the player but is
      --   not impacted back). Keep a handle on p.body to move/toggle it each frame.
      --   e.g. p.body = physics.RigidBody{ colliders = { box = CAR_BOX }, kinetic = true }
      p = { x = ax, z = az, heading = heading, body = nil }
      phantoms[car_num] = p
    end
    -- Smooth toward the new target (interpolate to avoid teleport/strobe).
    p.x = p.x + (ax - p.x) * 0.5
    p.z = p.z + (az - p.z) * 0.5
    p.heading = heading
    -- TODO: set the mesh BODY node transform from (p.x, p.z, p.heading).

    -- Collision gate (specs/13 §13.9): solid only when data is RTK-grade and fresh.
    if COLLIDABLE and p.body ~= nil then
      local solid = (quality >= COLLIDE_QUALITY_MIN) and not code60
      -- TODO(ac_physics): p.body:setTransform(p.x, p.z, p.heading) and
      --   p.body:setCollisionEnabled(solid)  -- ghost/pass-through when not solid
    end
  end
  -- TODO: reflect code60 (e.g. tint phantoms / show a banner).
end

-- CSP Lua entry points -------------------------------------------------------

function script.update(dt)
  parse_and_apply(read_frame())
end

function script.draw3D()
  -- Optional: debug-draw phantom markers until meshes are wired.
end
