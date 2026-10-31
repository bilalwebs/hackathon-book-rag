/**
 * Floating chat widget component for RAG chatbot.
 *
 * Provides persistent chat interface that appears on all pages,
 * allowing students to ask questions and receive AI responses.
 */

import React, { useState, useRef, useEffect } from "react";
import useDocusaurusContext from "@docusaurus/useDocusaurusContext";
import {
  chatService,
  ChatMessage,
  ChatRequest,
} from "../../services/chatService";
import styles from "./ChatWidget.module.css";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { remarkCitations } from "../../utils/citations";

export const ChatWidget: React.FC = () => {
  const { siteConfig } = useDocusaurusContext();
  const baseUrl = siteConfig.baseUrl;

  const resolveSourceUrl = (url: string) => {
    if (/^https?:\/\//i.test(url)) {
      return url;
    }

    const cleanUrl = url.startsWith("/") ? url.substring(1) : url;
    const origin =
      typeof window !== "undefined" ? window.location.origin : "";
    return `${origin}${baseUrl}${cleanUrl}`;
  };

  // State management
  const [isOpen, setIsOpen] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [inputValue, setInputValue] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Refs for auto-scroll
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  /**
   * Auto-scroll to bottom when new messages arrive
   */
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  /**
   * Focus input when widget opens
   */
  useEffect(() => {
    if (isOpen && inputRef.current) {
      inputRef.current.focus();
    }
  }, [isOpen]);

  /**
   * Handle sending a message to the chatbot
   */
  const handleSendMessage = async () => {
    const query = inputValue.trim();

    if (!query) {
      return; // Don't send empty messages
    }

    // Get selected text from page (if any)
    const selectedText = chatService.getSelectedText();

    // Add user message to chat
    const userMessage: ChatMessage = {
      role: "user",
      content: query,
      timestamp: new Date().toISOString(),
    };

    setMessages((prev) => [...prev, userMessage]);
    setInputValue(""); // Clear input
    setIsLoading(true);
    setError(null);

    try {
      // Prepare request
      const request: ChatRequest = {
        query,
        conversation_id: conversationId || undefined,
        selected_text: selectedText || undefined,
      };

      // Call chatbot API
      const response = await chatService.query(request);

      // Update conversation ID
      setConversationId(response.conversation_id);

      // Add assistant response to chat
      const assistantMessage: ChatMessage = {
        role: "assistant",
        content: response.answer,
        timestamp: response.timestamp,
        sources: response.sources,
      };

      setMessages((prev) => [...prev, assistantMessage]);
    } catch (err) {
      // Handle errors
      const errorMessage =
        err instanceof Error ? err.message : "An unexpected error occurred";
      setError(errorMessage);

      console.error("Chat error:", err);
    } finally {
      setIsLoading(false);
    }
  };

  /**
   * Handle Enter key to send (Shift+Enter for newline)
   */
  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage();
    }
  };

  /**
   * Toggle chat widget open/closed
   */
  const toggleChat = () => {
    setIsOpen(!isOpen);
  };

  /**
   * Clear conversation and start fresh
   */
  const handleClearChat = () => {
    setMessages([]);
    setConversationId(null);
    setError(null);
  };

  return (
    <div className={styles.chatWidget}>
      {/* Chat button (always visible) */}
      <button
        className={styles.chatButton}
        onClick={toggleChat}
        aria-label="Toggle chat"
      >
        {isOpen ? "✕" : "💬"}
      </button>

      {/* Chat window (only visible when open) */}
      {isOpen && (
        <div className={styles.chatWindow}>
          {/* Header */}
          <div className={styles.chatHeader}>
            <h3>AI Tutor</h3>
            <button
              className={styles.clearButton}
              onClick={handleClearChat}
              aria-label="Clear chat"
            >
              🗑️
            </button>
          </div>

          {/* Messages */}
          <div className={styles.messagesContainer}>
            {messages.length === 0 && (
              <div className={styles.welcomeMessage}>
                <p>
                  <strong>Welcome!</strong>
                </p>
                <p>I'm your AI tutor for Physical AI & Humanoid Robotics.</p>
                <p>
                  Ask me anything about ROS 2, Gazebo, NVIDIA Isaac, or VLA!
                </p>
                <p className={styles.hint}>
                  💡 Tip: Select text on the page and ask questions for
                  context-aware answers.
                </p>
              </div>
            )}

            {messages.map((msg, index) => (
              <div
                key={index}
                className={`${styles.message} ${styles[msg.role]}`}
              >
                <div className={styles.messageContent}>
                  <strong>{msg.role === "user" ? "You" : "AI Tutor"}:</strong>
                  <div className={styles.markdownContent}>
                    <ReactMarkdown
                      remarkPlugins={[
                        remarkGfm,
                        [
                          remarkCitations,
                          {
                            sources: msg.sources,
                            resolveUrl: resolveSourceUrl,
                          },
                        ],
                      ]}
                    >
                      {msg.content}
                    </ReactMarkdown>
                  </div>

                  {/* Show sources for assistant messages */}
                  {msg.role === "assistant" &&
                    msg.sources &&
                    msg.sources.length > 0 && (
                      <div className={styles.sources}>
                        <strong>Sources:</strong>
                        <ul>
                          {msg.sources.map((source, idx) => {
                            const fullUrl = resolveSourceUrl(source.url);
                            const sourceNumber = source.source_number;

                            return (
                              <li key={`${source.url}-${sourceNumber ?? "un-numbered"}-${idx}`}>
                                <a
                                  href={fullUrl}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                >
                                  {sourceNumber !== undefined &&
                                    sourceNumber !== null && (
                                      <>
                                        <strong>[Source {sourceNumber}]</strong>{" "}
                                      </>
                                    )}
                                  {source.module} - {source.chapter}
                                </a>
                              </li>
                            );
                          })}
                        </ul>
                      </div>
                    )}
                </div>
              </div>
            ))}

            {/* Loading indicator */}
            {isLoading && (
              <div className={`${styles.message} ${styles.assistant}`}>
                <div className={styles.messageContent}>
                  <strong>AI Tutor:</strong>
                  <p className={styles.loadingDots}>Thinking...</p>
                </div>
              </div>
            )}

            {/* Error message */}
            {error && (
              <div className={styles.errorMessage}>
                <strong>Error:</strong> {error}
              </div>
            )}

            <div ref={messagesEndRef} />
          </div>

          {/* Input area */}
          <div className={styles.inputContainer}>
            <textarea
              ref={inputRef}
              className={styles.input}
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Ask a question... (Enter to send, Shift+Enter for newline)"
              rows={2}
              disabled={isLoading}
            />
            <button
              className={styles.sendButton}
              onClick={handleSendMessage}
              disabled={!inputValue.trim() || isLoading}
              aria-label="Send message"
            >
              ➤
            </button>
          </div>
        </div>
      )}
    </div>
  );
};
