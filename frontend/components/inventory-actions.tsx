"use client";

import { useState } from "react";

import type { BlockOption, FloorOption, InventoryRoomItem } from "../lib/api";
import {
  buildConfirmationMessage,
  confirmAction,
  storeFlashMessage,
} from "../lib/action-feedback";
import { postAction } from "../lib/client-api";

type Props = {
  blocks: BlockOption[];
  floors: FloorOption[];
  rooms: InventoryRoomItem[];
};

const ROOM_TYPES = ["1_IN_ROOM", "2_IN_ROOM", "3_IN_ROOM", "4_IN_ROOM"];

export function InventoryActions({ blocks, floors, rooms }: Props) {
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  const [blockName, setBlockName] = useState("");
  const [floorBlockId, setFloorBlockId] = useState(blocks[0] ? String(blocks[0].id) : "");
  const [floorLabel, setFloorLabel] = useState("");
  const [selectedBlockId, setSelectedBlockId] = useState(blocks[0] ? String(blocks[0].id) : "");
  const selectedBlock = blocks.find((block) => String(block.id) === selectedBlockId) ?? null;
  const [selectedFloorId, setSelectedFloorId] = useState(floors[0] ? String(floors[0].id) : "");
  const selectedFloor = floors.find((floor) => String(floor.id) === selectedFloorId) ?? null;
  const [blockEditName, setBlockEditName] = useState(selectedBlock?.name ?? "");
  const [blockEditActive, setBlockEditActive] = useState(selectedBlock?.is_active ?? true);
  const [floorEditLabel, setFloorEditLabel] = useState(selectedFloor?.floor_label ?? "");
  const [floorEditActive, setFloorEditActive] = useState(selectedFloor?.is_active ?? true);

  const [createBlockId, setCreateBlockId] = useState(blocks[0] ? String(blocks[0].id) : "");
  const createFloorOptions = floors.filter((floor) => String(floor.block_id) === createBlockId);
  const [createFloorId, setCreateFloorId] = useState(
    createFloorOptions[0] ? String(createFloorOptions[0].id) : "",
  );
  const [roomCode, setRoomCode] = useState("");
  const [roomType, setRoomType] = useState("1_IN_ROOM");
  const [unitPrice, setUnitPrice] = useState("");
  const [isActive, setIsActive] = useState(true);

  const [selectedRoomId, setSelectedRoomId] = useState(rooms[0] ? String(rooms[0].room_id) : "");
  const selectedRoom = rooms.find((room) => String(room.room_id) === selectedRoomId) ?? null;
  const [editBlockId, setEditBlockId] = useState(selectedRoom ? String(selectedRoom.block_id) : createBlockId);
  const editFloorOptions = floors.filter((floor) => String(floor.block_id) === editBlockId);
  const [editFloorId, setEditFloorId] = useState(
    selectedRoom?.floor_id ? String(selectedRoom.floor_id) : editFloorOptions[0] ? String(editFloorOptions[0].id) : "",
  );
  const [editRoomCode, setEditRoomCode] = useState(selectedRoom?.room_code ?? "");
  const [editRoomType, setEditRoomType] = useState(selectedRoom?.room_type ?? "1_IN_ROOM");
  const [editUnitPrice, setEditUnitPrice] = useState(selectedRoom?.unit_price_per_bed.replace(/[^\d.]/g, "") ?? "");
  const [editIsActive, setEditIsActive] = useState(selectedRoom?.is_active ?? true);

  function syncSelectedRoom(roomId: string) {
    setSelectedRoomId(roomId);
    const room = rooms.find((item) => String(item.room_id) === roomId);
    if (!room) {
      return;
    }
    setEditBlockId(String(room.block_id));
    setEditFloorId(room.floor_id ? String(room.floor_id) : "");
    setEditRoomCode(room.room_code);
    setEditRoomType(room.room_type ?? "1_IN_ROOM");
    setEditUnitPrice(room.unit_price_per_bed.replace(/[^\d.]/g, ""));
    setEditIsActive(room.is_active);
  }

  function syncSelectedBlock(blockId: string) {
    setSelectedBlockId(blockId);
    const block = blocks.find((item) => String(item.id) === blockId);
    if (!block) return;
    setBlockEditName(block.name);
    setBlockEditActive(block.is_active);
  }

  function syncSelectedFloor(floorId: string) {
    setSelectedFloorId(floorId);
    const floor = floors.find((item) => String(item.id) === floorId);
    if (!floor) return;
    setFloorEditLabel(floor.floor_label);
    setFloorEditActive(floor.is_active);
  }

  async function runAction(
    path: string,
    payload: object,
    target = "/inventory",
    confirmation?: string,
  ) {
    if (confirmation && !(await confirmAction(confirmation))) {
      return;
    }
    setPending(true);
    setError(null);
    setMessage(null);
    try {
      const result = await postAction(path, payload);
      setMessage(result.message);
      storeFlashMessage({ tone: "success", message: result.message });
      window.location.assign(target);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Inventory action failed.");
    } finally {
      setPending(false);
    }
  }

  return (
    <section className="panel">
      <h3>Inventory actions</h3>
      <div className="stack">
        <details className="action-disclosure">
          <summary className="action-summary">Create block and floor</summary>
          <div className="action-card action-card-embedded">
            <div className="stack tight">
            <label className="field">
              <span>Block name</span>
              <input value={blockName} onChange={(event) => setBlockName(event.target.value)} placeholder="New block" />
            </label>
            <button
              className="button"
              disabled={pending || !blockName.trim()}
              onClick={() =>
                runAction(
                  "/inventory/blocks",
                  { name: blockName },
                  "/inventory",
                  buildConfirmationMessage("Create this block?", [`Block name: ${blockName.trim()}`]),
                )
              }
            >
              Create block
            </button>
            <label className="field">
              <span>Block for new floor</span>
              <select value={floorBlockId} onChange={(event) => setFloorBlockId(event.target.value)}>
                {blocks.map((block) => (
                  <option key={block.id} value={block.id}>
                    {block.name}
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              <span>Floor label</span>
              <input value={floorLabel} onChange={(event) => setFloorLabel(event.target.value)} placeholder="Ground floor" />
            </label>
            <button
              className="button ghost"
              disabled={pending || !floorBlockId || !floorLabel.trim()}
              onClick={() =>
                runAction(
                  "/inventory/floors",
                  {
                    block_id: Number(floorBlockId),
                    floor_label: floorLabel,
                  },
                  "/inventory",
                  buildConfirmationMessage("Create this floor?", [
                    `Block ID: ${floorBlockId}`,
                    `Floor label: ${floorLabel.trim()}`,
                  ]),
                )
              }
            >
              Create floor
            </button>
          </div>
          </div>
        </details>

        <details className="action-disclosure">
          <summary className="action-summary">Create room</summary>
          <div className="action-card action-card-embedded">
            <div className="stack tight">
            <div className="inline-actions">
              <label className="field">
                <span>Block</span>
                <select
                  value={createBlockId}
                  onChange={(event) => {
                    const nextBlockId = event.target.value;
                    setCreateBlockId(nextBlockId);
                    const nextFloors = floors.filter((floor) => String(floor.block_id) === nextBlockId);
                    setCreateFloorId(nextFloors[0] ? String(nextFloors[0].id) : "");
                  }}
                >
                  {blocks.map((block) => (
                    <option key={block.id} value={block.id}>
                      {block.name}
                    </option>
                  ))}
                </select>
              </label>
              <label className="field">
                <span>Floor</span>
                <select value={createFloorId} onChange={(event) => setCreateFloorId(event.target.value)}>
                  {createFloorOptions.map((floor) => (
                    <option key={floor.id} value={floor.id}>
                      {floor.floor_label}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            <div className="inline-actions">
              <label className="field">
                <span>Room code</span>
                <input value={roomCode} onChange={(event) => setRoomCode(event.target.value)} placeholder="A-101" />
              </label>
              <label className="field">
                <span>Room type</span>
                <select value={roomType} onChange={(event) => setRoomType(event.target.value)}>
                  {ROOM_TYPES.map((option) => (
                    <option key={option} value={option}>
                      {option}
                    </option>
                  ))}
                </select>
              </label>
              <label className="field">
                <span>Unit price/bed</span>
                <input value={unitPrice} onChange={(event) => setUnitPrice(event.target.value)} inputMode="decimal" placeholder="0.00" />
              </label>
            </div>
            <label className="field">
              <span>Status</span>
              <select value={isActive ? "active" : "inactive"} onChange={(event) => setIsActive(event.target.value === "active")}>
                <option value="active">Active</option>
                <option value="inactive">Inactive</option>
              </select>
            </label>
            <button
              className="button"
              disabled={pending || !createBlockId || !createFloorId || !roomCode.trim() || !unitPrice}
              onClick={() =>
                runAction(
                  "/inventory/rooms",
                  {
                    block_id: Number(createBlockId),
                    floor_id: Number(createFloorId),
                    room_code: roomCode,
                    room_type: roomType,
                    unit_price_per_bed: Number(unitPrice),
                    is_active: isActive,
                  },
                  "/inventory",
                  buildConfirmationMessage("Create this room?", [
                    `Room: ${roomCode.trim()}`,
                    `Type: ${roomType}`,
                    `Price per bed: ${unitPrice}`,
                  ]),
                )
              }
            >
              Create room
            </button>
          </div>
          </div>
        </details>

        {blocks.length ? (
          <details className="action-disclosure">
            <summary className="action-summary">Edit block and floor</summary>
            <div className="action-card action-card-embedded">
              <div className="stack tight">
              <label className="field">
                <span>Block</span>
                <select value={selectedBlockId} onChange={(event) => syncSelectedBlock(event.target.value)}>
                  {blocks.map((block) => (
                    <option key={block.id} value={block.id}>
                      {block.name}
                    </option>
                  ))}
                </select>
              </label>
              <div className="inline-actions">
                <label className="field">
                  <span>Block name</span>
                  <input value={blockEditName} onChange={(event) => setBlockEditName(event.target.value)} />
                </label>
                <label className="field">
                  <span>Status</span>
                  <select value={blockEditActive ? "active" : "inactive"} onChange={(event) => setBlockEditActive(event.target.value === "active")}>
                    <option value="active">Active</option>
                    <option value="inactive">Inactive</option>
                  </select>
                </label>
              </div>
              <button
                className="button ghost"
                disabled={pending || !selectedBlockId || !blockEditName.trim()}
                onClick={() =>
                  runAction(
                    `/inventory/blocks/${selectedBlockId}`,
                    {
                      name: blockEditName,
                      is_active: blockEditActive,
                    },
                    "/inventory",
                    buildConfirmationMessage("Save block changes?", [
                      `Block ID: ${selectedBlockId}`,
                      `Name: ${blockEditName.trim()}`,
                      `Status: ${blockEditActive ? "Active" : "Inactive"}`,
                    ]),
                  )
                }
              >
                Save block
              </button>
              {floors.length ? (
                <>
                  <label className="field">
                    <span>Floor</span>
                    <select value={selectedFloorId} onChange={(event) => syncSelectedFloor(event.target.value)}>
                      {floors.map((floor) => (
                        <option key={floor.id} value={floor.id}>
                          {floor.block_name} / {floor.floor_label}
                        </option>
                      ))}
                    </select>
                  </label>
                  <div className="inline-actions">
                    <label className="field">
                      <span>Floor label</span>
                      <input value={floorEditLabel} onChange={(event) => setFloorEditLabel(event.target.value)} />
                    </label>
                    <label className="field">
                      <span>Status</span>
                      <select value={floorEditActive ? "active" : "inactive"} onChange={(event) => setFloorEditActive(event.target.value === "active")}>
                        <option value="active">Active</option>
                        <option value="inactive">Inactive</option>
                      </select>
                    </label>
                  </div>
                  <button
                    className="button ghost"
                    disabled={pending || !selectedFloorId || !floorEditLabel.trim()}
                    onClick={() =>
                      runAction(
                        `/inventory/floors/${selectedFloorId}`,
                        {
                          floor_label: floorEditLabel,
                          is_active: floorEditActive,
                        },
                        "/inventory",
                        buildConfirmationMessage("Save floor changes?", [
                          `Floor ID: ${selectedFloorId}`,
                          `Label: ${floorEditLabel.trim()}`,
                          `Status: ${floorEditActive ? "Active" : "Inactive"}`,
                        ]),
                      )
                    }
                  >
                    Save floor
                  </button>
                </>
              ) : null}
            </div>
            </div>
          </details>
        ) : null}

        {rooms.length ? (
          <details className="action-disclosure">
            <summary className="action-summary">Edit room and pricing</summary>
            <div className="action-card action-card-embedded">
              <div className="stack tight">
              <label className="field">
                <span>Room</span>
                <select value={selectedRoomId} onChange={(event) => syncSelectedRoom(event.target.value)}>
                  {rooms.map((room) => (
                    <option key={room.room_id} value={room.room_id}>
                      {room.block_name} / {room.floor_label ?? "Unassigned"} / {room.room_code}
                    </option>
                  ))}
                </select>
              </label>
              <div className="inline-actions">
                <label className="field">
                  <span>Block</span>
                  <select
                    value={editBlockId}
                    onChange={(event) => {
                      const nextBlockId = event.target.value;
                      setEditBlockId(nextBlockId);
                      const nextFloors = floors.filter((floor) => String(floor.block_id) === nextBlockId);
                      setEditFloorId(nextFloors[0] ? String(nextFloors[0].id) : "");
                    }}
                  >
                    {blocks.map((block) => (
                      <option key={block.id} value={block.id}>
                        {block.name}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="field">
                  <span>Floor</span>
                  <select value={editFloorId} onChange={(event) => setEditFloorId(event.target.value)}>
                    {editFloorOptions.map((floor) => (
                      <option key={floor.id} value={floor.id}>
                        {floor.floor_label}
                      </option>
                    ))}
                  </select>
                </label>
              </div>
              <div className="inline-actions">
                <label className="field">
                  <span>Room code</span>
                  <input value={editRoomCode} onChange={(event) => setEditRoomCode(event.target.value)} />
                </label>
                <label className="field">
                  <span>Room type</span>
                  <select value={editRoomType} onChange={(event) => setEditRoomType(event.target.value)}>
                    {ROOM_TYPES.map((option) => (
                      <option key={option} value={option}>
                        {option}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="field">
                  <span>Unit price/bed</span>
                  <input value={editUnitPrice} onChange={(event) => setEditUnitPrice(event.target.value)} inputMode="decimal" />
                </label>
              </div>
              <label className="field">
                <span>Status</span>
                <select value={editIsActive ? "active" : "inactive"} onChange={(event) => setEditIsActive(event.target.value === "active")}>
                  <option value="active">Active</option>
                  <option value="inactive">Inactive</option>
                </select>
              </label>
              <button
                className="button"
                disabled={pending || !selectedRoomId || !editBlockId || !editFloorId || !editRoomCode.trim() || !editUnitPrice}
                onClick={() =>
                  runAction(
                    `/inventory/rooms/${selectedRoomId}`,
                    {
                      block_id: Number(editBlockId),
                      floor_id: Number(editFloorId),
                      room_code: editRoomCode,
                      room_type: editRoomType,
                      unit_price_per_bed: Number(editUnitPrice),
                      is_active: editIsActive,
                    },
                    "/inventory",
                    buildConfirmationMessage("Update this room?", [
                      `Room ID: ${selectedRoomId}`,
                      `Code: ${editRoomCode.trim()}`,
                      `Price per bed: ${editUnitPrice}`,
                      `Status: ${editIsActive ? "Active" : "Inactive"}`,
                    ]),
                  )
                }
              >
                Update room
              </button>
            </div>
            </div>
          </details>
        ) : null}

        {message ? <p className="success-text">{message}</p> : null}
        {error ? <p className="error-text">{error}</p> : null}
      </div>
    </section>
  );
}
