#include <autoconf.h>
#include <benchset/gen_config.h>

/* C includes */
#include <assert.h>
#include <sel4utils/process.h>

#include <sel4/sel4.h>

int
main(void)
{
#if defined(CONFIG_DEBUG_BUILD)
    seL4_DebugPutChar('H');
    seL4_DebugPutChar('e');
    seL4_DebugPutChar('l');
    seL4_DebugPutChar('l');
    seL4_DebugPutChar('o');
    seL4_DebugPutChar(' ');
    seL4_DebugPutChar('W');
    seL4_DebugPutChar('o');
    seL4_DebugPutChar('r');
    seL4_DebugPutChar('l');
    seL4_DebugPutChar('d');
    seL4_DebugPutChar('!');
    seL4_DebugPutChar('\n');
#endif
    seL4_Word badge;
    seL4_MessageInfo_t tag;
    seL4_MessageInfo_t reply_tag;

    tag = seL4_Recv(SEL4UTILS_ENDPOINT_SLOT, &badge, SEL4UTILS_REPLY_SLOT);
#if defined(CONFIG_DEBUG_BUILD)
    seL4_DebugPutChar('R');
    seL4_DebugPutChar('e');
    seL4_DebugPutChar('c');
    seL4_DebugPutChar('v');
    seL4_DebugPutChar('\n');
#endif
    /* To make this simpler this literally just always replies */
    while (1) {
        /* the reason we put the INPUT_CAP here is the call comes from it */
        tag = seL4_ReplyRecv(SEL4UTILS_ENDPOINT_SLOT, reply_tag, &badge, SEL4UTILS_REPLY_SLOT);
    }

    return 0;
}
