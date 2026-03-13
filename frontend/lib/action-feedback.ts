"use client";

export type FlashTone = "success" | "error" | "warning";
export type ConfirmationTone = "default" | "warning" | "danger";

export type FlashMessage = {
  tone: FlashTone;
  message: string;
  priority?: "primary" | "passive";
};

export type ConfirmationRequest = {
  message: string;
  resolve: (confirmed: boolean) => void;
};

const FLASH_STORAGE_KEY = "hostel-ops-flash-message";
export const FLASH_EVENT_NAME = "hostel-ops-flash";
export const CONFIRM_EVENT_NAME = "hostel-ops-confirm";

export function buildConfirmationMessage(
  title: string,
  lines: Array<string | null | undefined> = [],
): string {
  const detailLines = lines
    .map((line) => line?.trim())
    .filter((line): line is string => Boolean(line));
  return [title, ...detailLines.map((line) => `- ${line}`), "", "Continue?"].join("\n");
}

export function parseConfirmationMessage(message: string): {
  title: string;
  details: string[];
} {
  const lines = message
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter((line) => Boolean(line) && line !== "Continue?");
  const [title = "Confirm this action?", ...rest] = lines;
  return {
    title,
    details: rest.map((line) => (line.startsWith("- ") ? line.slice(2) : line)),
  };
}

export function confirmationToneForTitle(title: string): ConfirmationTone {
  const lower = title.toLowerCase();
  if (/(delete|cancel|void|reject|archive|disable|overwrite|remove)/.test(lower)) {
    return "danger";
  }
  if (/(reset|run|expire|re-queue|requeue|block)/.test(lower)) {
    return "warning";
  }
  return "default";
}

export function confirmationLabelForTitle(title: string): string {
  const match = title.match(/^([A-Za-z-]+)/);
  return match?.[1] ?? "Confirm";
}

export function flashTitleForTone(tone: FlashTone): string {
  if (tone === "success") {
    return "Action completed";
  }
  if (tone === "warning") {
    return "Review needed";
  }
  return "Action failed";
}

export function confirmAction(message: string): Promise<boolean> {
  if (typeof window === "undefined") {
    return Promise.resolve(true);
  }
  return new Promise<boolean>((resolve) => {
    window.dispatchEvent(
      new CustomEvent<ConfirmationRequest>(CONFIRM_EVENT_NAME, {
        detail: { message, resolve },
      }),
    );
  });
}

export function storeFlashMessage(flash: FlashMessage): void {
  if (typeof window === "undefined") {
    return;
  }
  window.sessionStorage.setItem(FLASH_STORAGE_KEY, JSON.stringify(flash));
  window.dispatchEvent(new CustomEvent<FlashMessage>(FLASH_EVENT_NAME, { detail: flash }));
}

export function storePassiveFlashMessage(message: Omit<FlashMessage, "priority">): void {
  storeFlashMessage({ ...message, priority: "passive" });
}

export function consumeFlashMessage(): FlashMessage | null {
  const value = peekFlashMessage();
  if (typeof window === "undefined" || !value) {
    return value;
  }
  window.sessionStorage.removeItem(FLASH_STORAGE_KEY);
  return value;
}

export function peekFlashMessage(): FlashMessage | null {
  if (typeof window === "undefined") {
    return null;
  }
  const rawValue = window.sessionStorage.getItem(FLASH_STORAGE_KEY);
  if (!rawValue) {
    return null;
  }
  try {
    return JSON.parse(rawValue) as FlashMessage;
  } catch {
    return null;
  }
}
