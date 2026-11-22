#pragma once
#include <algorithm>
#include <array>
#include <cstddef>
#include <cstdint>
#include <vector>

template<class Id, size_t Slots=1024>
class RegionBufferIndex {
    struct Segment { uint64_t begin,end; Id id; };
    struct Region {
        std::vector<Segment> entries;
        const void* owner=nullptr;
        uint64_t generation=0, region=0, epoch=0;
    };
    std::array<Region,Slots> regions;
public:
    template<class Populate,class Emit>
    void Visit(const void* owner,uint64_t generation,uint64_t region,uint64_t epoch,
               uint64_t begin,uint64_t end,Populate&& populate,Emit&& emit) {
        static_assert((Slots&(Slots-1))==0);
        auto& slot=regions[(region^(region>>10)^(region>>20))&(Slots-1)];
        if (slot.owner!=owner || slot.generation!=generation || slot.region!=region || slot.epoch!=epoch) {
            slot.entries.clear();
            populate([&](uint64_t first,uint64_t after,Id id) {
                slot.entries.push_back({first,after,id});
            });
            slot.owner=owner;
            slot.generation=generation;
            slot.region=region;
            slot.epoch=epoch;
        }
        // Match map::upper_bound(begin) and its predecessor, including holes, empty
        // regions, long buffers which began in an earlier region, and exact boundaries.
        auto it=std::upper_bound(slot.entries.begin(),slot.entries.end(),begin,
                                 [](uint64_t value,const Segment& item){return value<item.begin;});
        if(it!=slot.entries.begin()) --it;
        for(;it!=slot.entries.end() && it->begin<end;++it) {
            const auto first=std::max(begin,it->begin);
            const auto after=std::min(end,it->end);
            if(first<after) emit(it->id,first,after-first);
        }
    }
};
