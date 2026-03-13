"use client";

import { useEffect, useId, useRef, useState } from "react";

import type { ConfirmationRequest, FlashMessage } from "../lib/action-feedback";
import {
  confirmationLabelForTitle,
  confirmationToneForTitle,
  consumeFlashMessage,
  CONFIRM_EVENT_NAME,
  flashTitleForTone,
  FLASH_EVENT_NAME,
  parseConfirmationMessage,
} from "../lib/action-feedback";

export function GlobalFlash() {
  const [flash, setFlash] = useState<FlashMessage | null>(null);
  const [confirmations, setConfirmations] = useState<ConfirmationRequest[]>([]);
  const titleId = useId();
  const descriptionId = useId();
  const cancelButtonRef = useRef<HTMLButtonElement | null>(null);
  const confirmButtonRef = useRef<HTMLButtonElement | null>(null);
  const confirmationsRef = useRef<ConfirmationRequest[]>([]);
  const currentConfirmation = confirmations[0] ?? null;

  useEffect(() => {
    confirmationsRef.current = confirmations;
  }, [confirmations]);

  useEffect(() => {
    setFlash(consumeFlashMessage());
    const handleFlash = (event: Event) => {
      const customEvent = event as CustomEvent<FlashMessage>;
      if (customEvent.detail) {
        setFlash((current) => {
          if (customEvent.detail.priority === "passive" && current) {
            return current;
          }
          return customEvent.detail;
        });
      }
    };
    const handleConfirmation = (event: Event) => {
      const customEvent = event as CustomEvent<ConfirmationRequest>;
      if (customEvent.detail) {
        setConfirmations((current) => [...current, customEvent.detail]);
      }
    };

    window.addEventListener(FLASH_EVENT_NAME, handleFlash as EventListener);
    window.addEventListener(CONFIRM_EVENT_NAME, handleConfirmation as EventListener);
    return () => {
      window.removeEventListener(FLASH_EVENT_NAME, handleFlash as EventListener);
      window.removeEventListener(CONFIRM_EVENT_NAME, handleConfirmation as EventListener);
    };
  }, []);

  useEffect(() => {
    if (!flash || flash.tone === "error") {
      return;
    }
    const timeout = window.setTimeout(
      () => setFlash((current) => (current === flash ? null : current)),
      flash.tone === "warning" ? 6500 : 5500,
    );
    return () => window.clearTimeout(timeout);
  }, [flash]);

  useEffect(() => {
    if (!currentConfirmation) {
      return;
    }
    const previousActiveElement =
      document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    cancelButtonRef.current?.focus();

    const handleKeyDown = (event: KeyboardEvent) => {
      if (!currentConfirmation) {
        return;
      }
      if (event.key === "Escape") {
        event.preventDefault();
        currentConfirmation.resolve(false);
        setConfirmations((queue) => queue.slice(1));
        return;
      }
      if (event.key !== "Tab") {
        return;
      }
      const focusable = [cancelButtonRef.current, confirmButtonRef.current].filter(
        (element): element is HTMLButtonElement => Boolean(element),
      );
      if (!focusable.length) {
        return;
      }
      const currentIndex = focusable.findIndex((element) => element === document.activeElement);
      if (event.shiftKey) {
        if (currentIndex <= 0) {
          event.preventDefault();
          focusable[focusable.length - 1]?.focus();
        }
        return;
      }
      if (currentIndex === focusable.length - 1) {
        event.preventDefault();
        focusable[0]?.focus();
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => {
      window.removeEventListener("keydown", handleKeyDown);
      document.body.style.overflow = previousOverflow;
      previousActiveElement?.focus();
    };
  }, [currentConfirmation]);

  useEffect(() => {
    return () => {
      for (const confirmation of confirmationsRef.current) {
        confirmation.resolve(false);
      }
    };
  }, []);

  const parsedConfirmation = currentConfirmation
    ? parseConfirmationMessage(currentConfirmation.message)
    : null;
  const confirmationTone = parsedConfirmation
    ? confirmationToneForTitle(parsedConfirmation.title)
    : "default";
  const confirmationLabel = parsedConfirmation
    ? confirmationLabelForTitle(parsedConfirmation.title)
    : "Confirm";

  function dismissFlash() {
    setFlash(null);
  }

  function resolveConfirmation(confirmed: boolean) {
    if (!currentConfirmation) {
      return;
    }
    currentConfirmation.resolve(confirmed);
    setConfirmations((queue) => queue.slice(1));
  }

  if (!flash && !currentConfirmation) {
    return null;
  }

  return (
    <>
      {flash ? (
        <div
          className="feedback-toast-layer"
          aria-live={flash.tone === "error" ? "assertive" : "polite"}
        >
          <div
            className={`feedback-toast ${flash.tone}`}
            role={flash.tone === "error" ? "alert" : "status"}
          >
            <div className="feedback-toast-copy">
              <strong>{flashTitleForTone(flash.tone)}</strong>
              <span>{flash.message}</span>
            </div>
            <button className="button ghost small" onClick={dismissFlash} type="button">
              Dismiss
            </button>
          </div>
        </div>
      ) : null}

      {currentConfirmation && parsedConfirmation ? (
        <div className="feedback-dialog-layer">
          <div className="feedback-dialog-backdrop" />
          <div
            aria-describedby={descriptionId}
            aria-labelledby={titleId}
            aria-modal="true"
            className={`feedback-dialog ${confirmationTone}`}
            role="dialog"
          >
            <div className="feedback-dialog-copy">
              <span className={`feedback-dialog-kicker ${confirmationTone}`}>Confirm action</span>
              <h2 id={titleId}>{parsedConfirmation.title}</h2>
              <p id={descriptionId}>
                {parsedConfirmation.details.length
                  ? "Review the details below before continuing."
                  : "Confirm this action to continue."}
              </p>
            </div>
            {parsedConfirmation.details.length ? (
              <div className="feedback-dialog-details">
                {parsedConfirmation.details.map((detail) => (
                  <div key={detail} className="feedback-dialog-detail">
                    {detail}
                  </div>
                ))}
              </div>
            ) : null}
            <div className="feedback-dialog-actions">
              <button
                className="button ghost"
                data-feedback-cancel
                onClick={() => resolveConfirmation(false)}
                ref={cancelButtonRef}
                type="button"
              >
                Keep editing
              </button>
              <button
                className={
                  confirmationTone === "danger"
                    ? "button danger"
                    : confirmationTone === "warning"
                      ? "button warning"
                      : "button"
                }
                data-feedback-confirm
                onClick={() => resolveConfirmation(true)}
                ref={confirmButtonRef}
                type="button"
              >
                {confirmationLabel}
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </>
  );
}
