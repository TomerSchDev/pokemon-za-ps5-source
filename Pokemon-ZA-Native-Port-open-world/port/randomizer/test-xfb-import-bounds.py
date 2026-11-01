"""Exercise the real xm_prepare body with GPU allocation calls stubbed on host."""
from pathlib import Path
import json,re,subprocess,sys
root=Path(__file__).resolve().parents[2]
text=(Path(sys.argv[1])/'runtime/nvn/vulkan/exec.c').read_text()
body=text[text.index('static bool xm_prepare(void) {'):text.index('// a vertex stream inside the mirror',text.index('static bool xm_prepare(void) {'))]
macro=re.search(r'^#define GM_IN.*$',text,re.M).group()
prefix=r'''
#include <stdint.h>
#include <stdbool.h>
#include <stdio.h>
#include <string.h>
typedef uint64_t VkBuffer;
typedef uint64_t VmaAllocation;
typedef struct { uint64_t srcOffset,dstOffset,size; } VkBufferCopy;
typedef struct { int sType; uint64_t size; unsigned usage; } VkBufferCreateInfo;
typedef struct { int usage; } VmaAllocationCreateInfo;
enum { VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO=1,VK_BUFFER_USAGE_STORAGE_BUFFER_BIT=2,
VK_BUFFER_USAGE_VERTEX_BUFFER_BIT=4,VK_BUFFER_USAGE_TRANSFER_SRC_BIT=8,
VK_BUFFER_USAGE_TRANSFER_DST_BIT=16,VMA_MEMORY_USAGE_AUTO_PREFER_DEVICE=1,VK_SUCCESS=0,VK_NULL_HANDLE=0 };
static struct { int vma; } g_vk;
static int vmaCreateBuffer(int a,void*b,void*c,void*d,void*e,void*f){(void)a;(void)b;(void)c;(void)d;(void)e;(void)f;return 0;}
#define LOG(...) ((void)0)
#define XM_SIZE (64ull<<20)
#define XM_CHUNK 256ull
static VkBuffer xm_buf=1,gmem_buf=1;
static VmaAllocation xm_mem;
static uint64_t xm_lo,gwin_base,gmem_lo,gmem_size,xfb_addr[4],xfb_size[4],stat_xm_fallback;
static uint32_t xm_written[XM_SIZE/XM_CHUNK];
static VkBufferCopy xm_back[256];static int xm_back_n;
static bool xm_on(void){return true;}
static uint64_t vk_frame_counter(void){return 1;}
static bool xm_inside(uint64_t a,uint64_t n){return xm_lo&&a>=xm_lo&&a+n<=xm_lo+XM_SIZE;}
'''
suffix=r'''
static int check(uint64_t base,uint64_t lo,uint64_t len,uint64_t a,uint64_t n,bool expected){
 gwin_base=base;gmem_lo=lo;gmem_size=len;xm_lo=0;xm_back_n=0;
 memset(xfb_addr,0,sizeof xfb_addr);memset(xfb_size,0,sizeof xfb_size);
 xfb_addr[0]=a;xfb_size[0]=n;
 bool got=xm_prepare();
 if(got!=expected||(!expected&&xm_back_n)){fprintf(stderr,"wrong bounds decision: %llx+%llx expected=%d got=%d copies=%d\n",(unsigned long long)a,(unsigned long long)n,expected,got,xm_back_n);return 1;}
 if(got&&(xm_back[0].dstOffset>len||xm_back[0].size>len-xm_back[0].dstOffset))return 2;
 return 0;
}
int main(void){
 int e=0;
 e|=check(0x744fa80000,0,0x6980000,0x77334b9260,0x8a0,false);
 e|=check(0x744fa80000,0,0x6980000,0x744fa80000,16,true);
 e|=check(0x744fa80000,0,0x6980000,0x74563ffff0,32,false);
 e|=check(0x7676b00000,0xb9500000,0x10000000,0x77334b9260,0x8a0,true);
 e|=check(0x7676b00000,0xb9500000,0x10000000,0x7730000000-16,32,false);
 if(!e)puts("PASS: observed GPU fault range rejected, valid zero/nonzero-offset imports accepted, crossing ranges rejected");
 return e;
}
'''
out=root/'evidence/randomizer-r9-xfb-test';out.mkdir(exist_ok=True)
results={}
for name,method,want in [('fixed',body,0),('regression',body.replace('if (!GM_IN(xfb_addr[b], xfb_size[b]))','if (gmem_lo && !GM_IN(xfb_addr[b], xfb_size[b]))'),1)]:
    source=out/(name+'.c');exe=out/name;source.write_text(prefix+'\n'+macro+'\n'+method+suffix)
    subprocess.run(['clang-21','-std=c11','-Wall','-Wextra','-Werror',str(source),'-o',str(exe)],check=True)
    p=subprocess.run([str(exe)],capture_output=True,text=True)
    results[name]={'returncode':p.returncode,'stdout':p.stdout,'stderr':p.stderr}
    assert p.returncode==want,results[name]
(out/'verification.json').write_text(json.dumps(results,indent=2))
print(json.dumps(results,indent=2))
