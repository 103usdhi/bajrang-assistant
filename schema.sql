-- Enable the vector extension for semantic memory
CREATE EXTENSION IF NOT EXISTS vector;

-- Table for the master vocabulary list
CREATE TABLE IF NOT EXISTS german_vocabulary (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    word TEXT NOT NULL,
    article TEXT CHECK (article IN ('der', 'die', 'das')), -- Essential for A1 Article practice
    plural TEXT,                                         -- Essential for A1 plural practice
    meaning TEXT NOT NULL,
    example_sentence TEXT,
    level TEXT DEFAULT 'A1',                             -- 'A1', 'A2', etc.
    source TEXT,                                         -- 'Goethe', 'Netzwerk Neu', 'Personal'
    theme TEXT,                                          -- 'Restaurant', 'Doctor', 'Travel'
    created_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(word, article)
);

-- Table for tracking Spaced Repetition (SRS) progress
CREATE TABLE IF NOT EXISTS user_vocab_progress (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id BIGINT NOT NULL,                             -- Matches your ALLOWED_USER_ID
    word_id UUID REFERENCES german_vocabulary(id) ON DELETE CASCADE,
    
    -- SRS Metadata (SM-2 Algorithm)
    ease_factor DOUBLE PRECISION DEFAULT 2.5,            -- Multiplier for the interval (starts at 2.5)
    interval INTEGER DEFAULT 0,                          -- Days until next review
    repetitions INTEGER DEFAULT 0,                       -- Number of successful consecutive recalls
    
    -- Timing
    last_reviewed TIMESTAMPTZ,
    next_review TIMESTAMPTZ DEFAULT now(),
    
    -- Tracking mistakes
    total_mistakes INTEGER DEFAULT 0,
    
    UNIQUE(user_id, word_id)
);

-- Index for fast retrieval of words due for review
CREATE INDEX IF NOT EXISTS idx_next_review ON user_vocab_progress (user_id, next_review);

-- Table for persistent document storage
CREATE TABLE IF NOT EXISTS uploaded_documents (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    created_at TIMESTAMPTZ DEFAULT now(),
    filename TEXT NOT NULL,
    telegram_file_id TEXT NOT NULL,
    document_type TEXT,
    source TEXT,
    page_count INTEGER,
    extracted_text_summary TEXT,
    semantic_chunk_count INTEGER,
    storage_status TEXT DEFAULT 'telegram',
    local_processing_path TEXT
);

-- Index for document retrieval
CREATE INDEX IF NOT EXISTS idx_uploaded_docs_filename ON uploaded_documents (filename);
CREATE INDEX IF NOT EXISTS idx_uploaded_docs_created_at ON uploaded_documents (created_at);

-- Core Conversation Logs
CREATE TABLE IF NOT EXISTS events_log (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    created_at TIMESTAMPTZ DEFAULT now(),
    user_message TEXT,
    assistant_response TEXT,
    source TEXT DEFAULT 'telegram'
);

-- System Error Logs
CREATE TABLE IF NOT EXISTS system_logs (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    created_at TIMESTAMPTZ DEFAULT now(),
    module TEXT,
    error_message TEXT
);

-- Personal Memories
CREATE TABLE IF NOT EXISTS personal_memory (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    created_at TIMESTAMPTZ DEFAULT now(),
    memory_text TEXT NOT NULL,
    memory_type TEXT DEFAULT 'general',
    importance TEXT DEFAULT 'medium',
    source TEXT DEFAULT 'telegram',
    is_active BOOLEAN DEFAULT true
);

-- Semantic Memory (requires pgvector extension)
-- Run: CREATE EXTENSION IF NOT EXISTS vector;
CREATE TABLE IF NOT EXISTS semantic_memory (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    created_at TIMESTAMPTZ DEFAULT now(),
    content TEXT NOT NULL,
    source TEXT DEFAULT 'telegram',
    embedding vector(1536) -- Match OpenAI text-embedding-3-small
);

-- Finance Transactions
CREATE TABLE IF NOT EXISTS finance_transactions (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    created_at TIMESTAMPTZ DEFAULT now(),
    amount DECIMAL(12,2) NOT NULL,
    currency TEXT DEFAULT 'EUR',
    transaction_type TEXT,
    category TEXT,
    is_essential BOOLEAN DEFAULT false,
    description TEXT
);

-- Table for German grammar notes (Required by handle_german_grammar_flow)
CREATE TABLE IF NOT EXISTS german_grammar (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    topic TEXT NOT NULL,
    note TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Semantic search function for vector retrieval
CREATE OR REPLACE FUNCTION match_semantic_memory (
  query_embedding vector(1536),
  match_threshold float,
  match_count int
)
RETURNS TABLE (
  id uuid,
  content text,
  source text,
  similarity float
)
LANGUAGE plpgsql
AS $$
BEGIN
  RETURN QUERY
  SELECT
    sm.id,
    sm.content,
    sm.source,
    1 - (sm.embedding <=> query_embedding) AS similarity
  FROM semantic_memory sm
  WHERE 1 - (sm.embedding <=> query_embedding) > match_threshold
  ORDER BY similarity DESC
  LIMIT match_count;
END;
$$;