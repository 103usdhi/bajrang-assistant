-- Table for the master vocabulary list
CREATE TABLE german_vocabulary (
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
CREATE TABLE user_vocab_progress (
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
CREATE INDEX idx_next_review ON user_vocab_progress (user_id, next_review);