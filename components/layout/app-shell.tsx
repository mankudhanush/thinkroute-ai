"use client";

import { motion } from "framer-motion";
import { ConversationPanel } from "@/components/chat/conversation-panel";
import { Panel } from "@/components/layout/panel";
import { DiffPanel } from "@/components/routing/diff-panel";
import { InferencePanel } from "@/components/routing/inference-panel";
import { ProviderSidebar } from "@/components/sidebar/provider-sidebar";
import { ToastNotifications } from "@/components/ui/toast-notifications";

export function AppShell() {
  return (
    <main className="h-dvh overflow-y-auto bg-[radial-gradient(circle_at_top_left,hsl(193_58%_48%/0.10),transparent_34%),hsl(var(--background))] lg:grid lg:grid-cols-[320px_minmax(0,1fr)_340px] lg:overflow-hidden">
      <motion.div
        initial={{ opacity: 0, x: -10 }}
        animate={{ opacity: 1, x: 0 }}
        transition={{ duration: 0.24 }}
        className="min-w-0"
      >
        <Panel className="border-r lg:h-dvh">
          <ProviderSidebar />
        </Panel>
      </motion.div>
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.24, delay: 0.04 }}
        className="min-w-0"
      >
        <Panel className="lg:h-dvh">
          <ConversationPanel />
        </Panel>
      </motion.div>
      <motion.div
        initial={{ opacity: 0, x: 10 }}
        animate={{ opacity: 1, x: 0 }}
        transition={{ duration: 0.24, delay: 0.08 }}
        className="min-w-0"
      >
        <Panel className="border-l lg:h-dvh">
          <InferencePanel />
        </Panel>
      </motion.div>
      <ToastNotifications />
      <DiffPanel />
    </main>
  );
}
