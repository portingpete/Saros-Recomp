#include "regionBufferIndex.h"
#include <cassert>
#include <cstdio>
#include <map>
#include <random>
#include <tuple>

int main() {
    constexpr uint64_t size=4096, regions=64;
    using Result=std::vector<std::tuple<unsigned,uint64_t,uint64_t>>;
    std::map<uint64_t,std::pair<uint64_t,unsigned>> live;
    RegionBufferIndex<unsigned,8> index;
    std::array<uint64_t,regions> epochs{};
    uint64_t generation=1,version=1,trials=0;
    unsigned next_id=1;
    std::mt19937 rng(0x51073);
    auto changed=[&](uint64_t begin,uint64_t end) {
        ++version;
        for(auto r=begin/size;r<=(end-1)/size;++r) epochs[r]=version;
    };
    auto visit=[&](uint64_t first,uint64_t end,const auto& emit) {
        auto it=live.upper_bound(first);
        if(it!=live.begin()) --it;
        for(;it!=live.end() && it->first<end;++it)
            emit(it->first,it->second.first,it->second.second);
    };
    auto check=[&](uint64_t begin,uint64_t end) {
        const uint64_t region=begin/size;
        assert(region==(end-1)/size);
        Result want,got;
        visit(begin,end,[&](uint64_t a,uint64_t b,unsigned id){
            a=std::max(a,begin);b=std::min(b,end);
            if(a<b) want.emplace_back(id,a,b-a);
        });
        index.Visit(&live,generation,region,epochs[region],begin,end,
                    [&](const auto& append){visit(region*size,(region+1)*size,append);},
                    [&](unsigned id,uint64_t a,uint64_t len){got.emplace_back(id,a,len);});
        assert(got==want);
        ++trials;
    };
    for(unsigned step=0;step<24000;++step) {
        if(step%700==0) {
            live.clear();epochs.fill(0);version=1;++generation;next_id=1;
        }
        uint64_t a=rng()%(regions*size), b=std::min(a+1+rng()%(3*size), regions*size);
        auto pos=live.upper_bound(a);
        if(pos!=live.begin() && std::prev(pos)->second.first>a) {
            if(rng()%3==0) {
                auto old=std::prev(pos);changed(old->first,old->second.first);live.erase(old);
            }
        } else {
            if(pos!=live.end()) b=std::min(b,pos->first);
            if(a<b) { live[a]={b,next_id++};changed(a,b); }
        }
        for(unsigned repeat=0;repeat<5;++repeat) {
            const uint64_t r=rng()%regions, first=r*size, end=first+size;
            const uint64_t x=first+rng()%size;
            const uint64_t y=x+1+rng()%(end-x);
            check(first,end);check(x,y);check(x,x+1);check(x,y);check(end-1,end);
        }
    }
    std::printf("%llu ordered range comparisons matched\n",static_cast<unsigned long long>(trials));
}
