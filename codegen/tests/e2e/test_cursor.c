#include "runtime.c"
#include "unity.h"

void
setUp(void)
{
}

void
tearDown(void)
{
}

void
test_cursor_init(void)
{
    uint8_t buff[2] = {0};
    cursor_init(c, buff, 2);
    TEST_ASSERT_EQUAL_INT(2, c.len);
    TEST_ASSERT_EQUAL_INT(0, c.pos);
    TEST_ASSERT_EQUAL_PTR(buff, c.ptr);
}

void
test_cursor_push(void)
{
    uint8_t exe = 0, buff[6] = {0};
    cursor_init(c, buff, sizeof(buff));

    cursor_push_safe(&c, '1');
    TEST_ASSERT_EQUAL_INT(1, c.pos);
    TEST_ASSERT_EQUAL_MEMORY("1\0\0\0\0\0", buff, 6);
    exe++;

    cursor_push_safe(&c, '2');
    TEST_ASSERT_EQUAL_INT(2, c.pos);
    TEST_ASSERT_EQUAL_MEMORY("12\0\0\0\0", buff, 6);
    exe++;

    cursor_push_safe(&c, '3');
    TEST_ASSERT_EQUAL_INT(3, c.pos);
    TEST_ASSERT_EQUAL_MEMORY("123\0\0\0", buff, 6);
    exe++;

    cursor_push_safe(&c, '4');
    TEST_ASSERT_EQUAL_INT(4, c.pos);
    TEST_ASSERT_EQUAL_MEMORY("1234\0\0", buff, 6);
    exe++;

    cursor_push_safe(&c, '5');
    TEST_ASSERT_EQUAL_INT(5, c.pos);
    TEST_ASSERT_EQUAL_MEMORY("12345\0", buff, 6);
    exe++;

    cursor_push_safe(&c, '6');
    TEST_ASSERT_EQUAL_INT(6, c.pos);
    TEST_ASSERT_EQUAL_MEMORY("123456", buff, 6);
    exe++;

    cursor_push_safe(&c, '7'); // goto is called
    exe++;                     // should not happen!

fail:
    TEST_ASSERT_EQUAL_INT(6, exe);
}

void
test_cursor_copy(void)
{
    uint8_t exe = 0, buff[6] = {0};
    cursor_init(c, buff, sizeof(buff));

    cursor_copy_safe(&c, "123", 3);
    TEST_ASSERT_EQUAL_INT(3, c.pos);
    TEST_ASSERT_EQUAL_MEMORY("123\0\0\0", buff, 6);
    exe++;

    cursor_copy_safe(&c, "456", 3);
    TEST_ASSERT_EQUAL_INT(6, c.pos);
    TEST_ASSERT_EQUAL_MEMORY("123456", buff, 6);
    exe++;

    cursor_copy_safe(&c, "7", 1); // goto is called
    exe++;                        // should not happen!

fail:
    TEST_ASSERT_EQUAL_INT(2, exe);
}

int
main(void)
{
    UNITY_BEGIN();
    RUN_TEST(test_cursor_init);
    RUN_TEST(test_cursor_push);
    RUN_TEST(test_cursor_copy);
    return UNITY_END();
}
