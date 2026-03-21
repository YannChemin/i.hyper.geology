MODULE_TOPDIR = ../../..

include $(MODULE_TOPDIR)/include/Make/Dir.make

TESTS = test_i_hyper_geology.py

default: parsertest

parsertest:
	@for test in $(TESTS) ; do \
		echo "Running $$test..." ; \
		$(MODULE_TOPDIR)/tools/gunittest/testrunner.py $$test ; \
	done

.PHONY: default parsertest
