"use client";

// FIX_ROUND_2026-11-12 1a: one admin overview card that crashes while drawing shows its own inline error with a retry;
// the other cards and the page stay (never the page's "something went wrong").
import React from "react";
import { useTranslation } from "@/lib/i18n/context";
import { ErrorState } from "@/components/ui";

function CardCrashed({ onRetry }: { onRetry: () => void }) {
  const { t } = useTranslation();
  return <ErrorState variant="inline" message={t("lms.errors.unknown")} onRetry={onRetry} />;
}

interface Props {
  children: React.ReactNode;
  /** Loads the card's data again (the boundary resets once `resetKey` changes); without it the retry redraws. */
  onRetry?: () => void;
  /** The card's data: a new value draws the card again. */
  resetKey?: unknown;
}

interface State {
  crashed: boolean;
  key: unknown;
}

export class CardBoundary extends React.Component<Props, State> {
  state: State = { crashed: false, key: this.props.resetKey };

  static getDerivedStateFromProps(props: Props, state: State): Partial<State> | null {
    return props.resetKey !== state.key ? { crashed: false, key: props.resetKey } : null;
  }

  static getDerivedStateFromError(): Partial<State> {
    return { crashed: true };
  }

  private retry = () => {
    if (this.props.onRetry) this.props.onRetry();
    else this.setState({ crashed: false });
  };

  render() {
    return this.state.crashed ? <CardCrashed onRetry={this.retry} /> : this.props.children;
  }
}
