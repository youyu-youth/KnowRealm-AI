CREATE TABLE courses (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL CHECK (length(trim(name)) BETWEEN 1 AND 100),
    learning_context TEXT NOT NULL CHECK (
        learning_context IN ('SCHOOL', 'CAREER', 'INTEREST')
    ),
    education_stage TEXT CHECK (
        education_stage IS NULL OR education_stage IN (
            'MIDDLE_SCHOOL', 'HIGH_SCHOOL', 'UNDERGRADUATE', 'GRADUATE', 'DOCTORAL'
        )
    ),
    depth TEXT CHECK (
        depth IS NULL OR depth IN ('BEGINNER', 'INTERMEDIATE', 'ADVANCED')
    ),
    course_type TEXT CHECK (
        course_type IS NULL OR course_type IN ('MAJOR', 'GENERAL', 'ELECTIVE')
    ),
    description TEXT,
    hot_words TEXT,
    status TEXT NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE', 'ARCHIVED')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    deleted_at TEXT,
    CHECK (
        (learning_context = 'SCHOOL' AND education_stage IS NOT NULL AND depth IS NULL)
        OR
        (learning_context IN ('CAREER', 'INTEREST') AND education_stage IS NULL AND depth IS NOT NULL)
    )
);

CREATE INDEX idx_courses_updated_at ON courses(updated_at DESC);
CREATE INDEX idx_courses_learning_context ON courses(learning_context);
CREATE INDEX idx_courses_course_type ON courses(course_type);
